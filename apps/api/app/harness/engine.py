from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal, Mapping

from app.harness.models import OperatorRecord
from app.harness.serialization import jsonable, payload_hash
from app.harness.store import FileHarnessStore


_OPERATOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _identity(value: Any) -> Any:
    return value


class HarnessGraphError(ValueError):
    """Signal an invalid operator graph before execution starts."""


class HarnessExecutionError(RuntimeError):
    """Wrap an unexpected operator failure after recording it."""

    def __init__(self, operator: str, cause: Exception) -> None:
        super().__init__(f"Harness operator {operator!r} failed: {cause}")
        self.operator = operator
        self.cause = cause


class HarnessReplayError(RuntimeError):
    """Signal that replay cannot proceed without executing an operator."""


class OperatorBlocked(RuntimeError):
    """Signal an intentional policy block."""


class OperatorSkipped(RuntimeError):
    """Signal an intentional no-op."""


@dataclass(frozen=True)
class HarnessOperator:
    name: str
    run: Callable[["HarnessContext"], Any]
    version: str = "1"
    dependencies: tuple[str, ...] = ()
    dump: Callable[[Any], Any] = _identity
    load: Callable[[Any], Any] | None = None
    resumable: bool = False

    def __post_init__(self) -> None:
        if not _OPERATOR_NAME.fullmatch(self.name):
            raise ValueError(f"Invalid harness operator name: {self.name!r}")


@dataclass(frozen=True)
class HarnessContext:
    run_id: str
    initial_values: Mapping[str, Any]
    outputs: Mapping[str, Any]
    store: FileHarnessStore

    def get(self, name: str, default: Any = None) -> Any:
        if name in self.outputs:
            return self.outputs[name]
        return self.initial_values.get(name, default)


class ResearchHarness:
    """Execute a validated operator graph with file-backed lifecycle checkpoints."""

    def __init__(self, store: FileHarnessStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id

    async def run(
        self,
        operators: list[HarnessOperator],
        initial_values: Mapping[str, Any] | None = None,
        *,
        mode: Literal["execute", "resume", "replay"] = "resume",
    ) -> dict[str, Any]:
        if mode not in {"execute", "resume", "replay"}:
            raise ValueError(f"Unsupported harness mode: {mode}")
        ordered = _ordered_operators(operators)
        initial = dict(initial_values or {})
        initial_hash = payload_hash(jsonable(initial))
        if mode == "replay" and not self.store.has_manifest(self.run_id):
            raise HarnessReplayError(f"Replay requires an existing harness run: {self.run_id}")
        if mode != "replay":
            self.store.initialize(self.run_id, {"initialHash": initial_hash})
        outputs: dict[str, Any] = {}
        output_hashes: dict[str, str] = {}

        for operator in ordered:
            context = HarnessContext(self.run_id, initial, outputs, self.store)
            input_hash = payload_hash({
                "initialHash": initial_hash,
                "dependencies": {
                    dependency: output_hashes[dependency]
                    for dependency in operator.dependencies
                },
            })
            checkpoint = (
                self.store.read_checkpoint(self.run_id, operator.name)
                if mode in {"resume", "replay"}
                else None
            )
            checkpoint_matches = (
                checkpoint is not None
                and operator.resumable
                and operator.load is not None
                and checkpoint.version == operator.version
                and checkpoint.inputHash == input_hash
            )
            if checkpoint_matches:
                try:
                    outputs[operator.name] = operator.load(checkpoint.payload)
                except Exception as exc:  # noqa: BLE001
                    self._record_failure(operator, input_hash, exc)
                    raise HarnessExecutionError(operator.name, exc) from exc
                output_hashes[operator.name] = checkpoint.outputHash
                self._record(
                    operator,
                    status="resumed",
                    input_hash=input_hash,
                    output_hash=checkpoint.outputHash,
                    completed=True,
                )
                self.store.append_event(self.run_id, {
                    "type": "operator_replayed" if mode == "replay" else "operator_resumed",
                    "operator": operator.name,
                    "version": operator.version,
                })
                continue
            if mode == "replay":
                raise HarnessReplayError(
                    f"Replay requires a matching resumable checkpoint for operator {operator.name!r}."
                )

            previous = self.store.read_manifest(self.run_id).operators.get(operator.name)
            attempts = (previous.attempts if previous else 0) + 1
            self._record(
                operator,
                status="running",
                attempts=attempts,
                input_hash=input_hash,
            )
            self.store.append_event(self.run_id, {
                "type": "operator_started",
                "operator": operator.name,
                "version": operator.version,
                "attempt": attempts,
            })
            try:
                value = operator.run(context)
                if inspect.isawaitable(value):
                    value = await value
            except OperatorSkipped as exc:
                output_hash = payload_hash(None)
                self._record(
                    operator,
                    status="skipped",
                    attempts=attempts,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    message=str(exc)[:500],
                    completed=True,
                )
                self.store.append_event(self.run_id, {
                    "type": "operator_skipped",
                    "operator": operator.name,
                    "message": str(exc)[:500],
                })
                outputs[operator.name] = None
                output_hashes[operator.name] = output_hash
                continue
            except OperatorBlocked as exc:
                self._record(
                    operator,
                    status="blocked",
                    attempts=attempts,
                    input_hash=input_hash,
                    message=str(exc)[:500],
                    completed=True,
                )
                self.store.append_event(self.run_id, {
                    "type": "operator_blocked",
                    "operator": operator.name,
                    "message": str(exc)[:500],
                })
                raise
            except Exception as exc:  # noqa: BLE001
                self._record_failure(operator, input_hash, exc, attempts=attempts)
                raise HarnessExecutionError(operator.name, exc) from exc

            try:
                payload = jsonable(operator.dump(value))
                checkpoint = self.store.write_checkpoint(
                    self.run_id,
                    operator.name,
                    version=operator.version,
                    input_hash=input_hash,
                    payload=payload,
                )
            except Exception as exc:  # noqa: BLE001
                self._record_failure(operator, input_hash, exc, attempts=attempts)
                raise HarnessExecutionError(operator.name, exc) from exc
            outputs[operator.name] = value
            output_hashes[operator.name] = checkpoint.outputHash
            self._record(
                operator,
                status="completed",
                attempts=attempts,
                input_hash=input_hash,
                output_hash=checkpoint.outputHash,
                completed=True,
            )
            self.store.append_event(self.run_id, {
                "type": "operator_completed",
                "operator": operator.name,
                "version": operator.version,
                "outputHash": checkpoint.outputHash,
            })

        return outputs

    def _record_failure(
        self,
        operator: HarnessOperator,
        input_hash: str,
        error: Exception,
        *,
        attempts: int | None = None,
    ) -> None:
        self._record(
            operator,
            status="failed",
            attempts=attempts,
            input_hash=input_hash,
            message=str(error)[:500],
            completed=True,
        )
        self.store.append_event(self.run_id, {
            "type": "operator_failed",
            "operator": operator.name,
            "errorType": type(error).__name__,
            "message": str(error)[:500],
        })

    def _record(
        self,
        operator: HarnessOperator,
        *,
        status: str,
        attempts: int | None = None,
        input_hash: str = "",
        output_hash: str = "",
        message: str = "",
        completed: bool = False,
    ) -> None:
        previous = self.store.read_manifest(self.run_id).operators.get(operator.name)
        now = datetime.now().isoformat(timespec="milliseconds")
        record = OperatorRecord(
            name=operator.name,
            version=operator.version,
            status=status,
            attempts=attempts if attempts is not None else (previous.attempts if previous else 0),
            startedAt=(previous.startedAt if previous and previous.startedAt else now),
            completedAt=now if completed else "",
            message=message,
            inputHash=input_hash,
            outputHash=output_hash,
        )
        self.store.update_operator(self.run_id, record)


def _ordered_operators(operators: list[HarnessOperator]) -> list[HarnessOperator]:
    by_name: dict[str, HarnessOperator] = {}
    for operator in operators:
        if operator.name in by_name:
            raise HarnessGraphError(f"Duplicate operator name: {operator.name}")
        by_name[operator.name] = operator

    names = set(by_name)
    for operator in operators:
        unknown = [dependency for dependency in operator.dependencies if dependency not in names]
        if unknown:
            raise HarnessGraphError(
                f"Operator {operator.name!r} has unknown dependencies: {', '.join(unknown)}"
            )

    ordered: list[HarnessOperator] = []
    completed: set[str] = set()
    pending = list(operators)
    while pending:
        ready = [operator for operator in pending if set(operator.dependencies).issubset(completed)]
        if not ready:
            cycle = ", ".join(operator.name for operator in pending)
            raise HarnessGraphError(f"Operator dependency cycle: {cycle}")
        for operator in ready:
            ordered.append(operator)
            completed.add(operator.name)
            pending.remove(operator)
    return ordered
