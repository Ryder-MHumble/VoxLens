from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pydantic import ValidationError

from app.harness.models import HarnessCheckpoint, HarnessManifest, OperatorRecord
from app.harness.serialization import jsonable, payload_hash


_OPERATOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_SNAPSHOT_FILES = {
    "artifacts.jsonl": "artifact",
    "evidence.jsonl": "evidence",
    "claims.jsonl": "claim",
    "claim-evidence.jsonl": "claim_evidence",
    "verifications.jsonl": "verification",
}


class HarnessStoreError(RuntimeError):
    """Signal corrupt or unreadable persisted harness state."""


class FileHarnessStore:
    """Persist one single-writer research harness under each existing run directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def has_manifest(self, run_id: str) -> bool:
        return (self.root / _safe_run_id(run_id) / "harness.json").is_file()

    def initialize(self, run_id: str, metadata: dict[str, Any] | None = None) -> HarnessManifest:
        path = self._manifest_path(run_id)
        incoming_metadata = jsonable(dict(metadata or {}))
        if path.exists():
            manifest = self.read_manifest(run_id)
            if not incoming_metadata:
                return manifest
            merged_metadata = {**manifest.metadata, **incoming_metadata}
            if merged_metadata == manifest.metadata:
                return manifest
            updated = manifest.model_copy(update={
                "metadata": merged_metadata,
                "updatedAt": _now(),
            })
            self._atomic_write_json(path, updated.model_dump(mode="json"))
            return updated
        now = _now()
        manifest = HarnessManifest(
            runId=run_id,
            createdAt=now,
            updatedAt=now,
            metadata=incoming_metadata,
        )
        self._atomic_write_json(path, manifest.model_dump(mode="json"))
        return manifest

    def read_manifest(self, run_id: str) -> HarnessManifest:
        path = self._manifest_path(run_id)
        try:
            return HarnessManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise HarnessStoreError(f"Invalid harness manifest for {run_id}: {exc}") from exc

    def update_operator(self, run_id: str, record: OperatorRecord) -> HarnessManifest:
        _validate_operator_name(record.name)
        manifest = self.initialize(run_id)
        operators = dict(manifest.operators)
        operators[record.name] = record
        updated = manifest.model_copy(update={"operators": operators, "updatedAt": _now()})
        self._atomic_write_json(self._manifest_path(run_id), updated.model_dump(mode="json"))
        return updated

    def write_checkpoint(
        self,
        run_id: str,
        operator: str,
        *,
        version: str,
        input_hash: str,
        payload: Any,
    ) -> HarnessCheckpoint:
        _validate_operator_name(operator)
        self.initialize(run_id)
        normalized_payload = jsonable(payload)
        checkpoint = HarnessCheckpoint(
            operator=operator,
            version=version,
            inputHash=input_hash,
            outputHash=payload_hash(normalized_payload),
            committedAt=_now(),
            payload=normalized_payload,
        )
        self._atomic_write_json(
            self._checkpoint_path(run_id, operator),
            checkpoint.model_dump(mode="json"),
        )
        return checkpoint

    def read_checkpoint(self, run_id: str, operator: str) -> HarnessCheckpoint | None:
        _validate_operator_name(operator)
        path = self._checkpoint_path(run_id, operator)
        if not path.exists():
            return None
        try:
            checkpoint = HarnessCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise HarnessStoreError(f"Invalid checkpoint for {run_id}/{operator}: {exc}") from exc
        if checkpoint.operator != operator:
            raise HarnessStoreError(
                f"Checkpoint operator mismatch for {run_id}/{operator}: {checkpoint.operator}"
            )
        if checkpoint.outputHash != payload_hash(checkpoint.payload):
            raise HarnessStoreError(f"Checkpoint output hash mismatch for {run_id}/{operator}")
        return checkpoint

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        self.initialize(run_id)
        existing = list(self.iter_events(run_id))
        stored = {
            **jsonable(event),
            "schemaVersion": 1,
            "sequence": int(existing[-1]["sequence"]) + 1 if existing else 1,
            "writtenAt": _now(),
        }
        path = self._events_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(stored, ensure_ascii=False, sort_keys=True, default=str) + "\n").encode("utf-8")
        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._fsync_directory(path.parent)
        return stored

    def iter_events(self, run_id: str) -> Iterable[dict[str, Any]]:
        path = self._events_path(run_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        events.append(json.loads(line))
        except (OSError, ValueError) as exc:
            raise HarnessStoreError(f"Invalid harness event log for {run_id}: {exc}") from exc
        return events

    def write_pipeline_snapshot(self, run_id: str, result: Any) -> None:
        snapshots = {
            "artifacts.jsonl": result.acquisition_batch.raw_artifacts,
            "evidence.jsonl": result.evidence_batch.evidence_units,
            "claims.jsonl": result.claim_set.claims,
            "claim-evidence.jsonl": result.claim_set.claim_evidence_links,
            "verifications.jsonl": result.verified_report.verification_results,
        }
        run_dir = self._run_dir(run_id)
        snapshots_dir = run_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        generation = uuid4().hex
        temporary = snapshots_dir / f".{generation}.tmp"
        committed = snapshots_dir / generation
        temporary.mkdir(mode=0o700)
        try:
            for filename, values in snapshots.items():
                self._write_jsonl_path(temporary / filename, _snapshot_kind(filename), values)
            os.replace(temporary, committed)
            self._fsync_directory(snapshots_dir)
            self._atomic_write_json(
                run_dir / "snapshot.json",
                {
                    "schemaVersion": 1,
                    "generation": generation,
                    "committedAt": _now(),
                    "files": list(snapshots),
                },
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def read_jsonl(self, run_id: str, filename: str) -> list[dict[str, Any]]:
        active = self._active_snapshot(run_id)
        if active is None:
            return []
        _, directory = active
        return self._read_jsonl_path(run_id, filename, directory / filename)

    def read_pipeline_snapshot(self, run_id: str) -> dict[str, Any] | None:
        active = self._active_snapshot(run_id)
        if active is None:
            return None
        pointer, directory = active
        return {
            "schemaVersion": 1,
            "generation": pointer["generation"],
            "committedAt": pointer["committedAt"],
            "files": {
                filename: self._read_jsonl_path(run_id, filename, directory / filename)
                for filename in _SNAPSHOT_FILES
            },
        }

    def _read_jsonl_path(
        self,
        run_id: str,
        filename: str,
        path: Path,
    ) -> list[dict[str, Any]]:
        kind = _snapshot_kind(filename)
        records: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record.get("schemaVersion") != 1 or record.get("kind") != kind:
                        raise ValueError("snapshot record schema or kind mismatch")
                    if record.get("payloadHash") != payload_hash(record.get("payload")):
                        raise ValueError("snapshot payload hash mismatch")
                    records.append(record)
        except (OSError, ValueError) as exc:
            raise HarnessStoreError(f"Invalid harness snapshot {run_id}/{filename}: {exc}") from exc
        return records

    def _run_dir(self, run_id: str) -> Path:
        path = self.root / _safe_run_id(run_id)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def _manifest_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "harness.json"

    def _events_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "harness-events.jsonl"

    def _checkpoint_path(self, run_id: str, operator: str) -> Path:
        _validate_operator_name(operator)
        return self._run_dir(run_id) / "checkpoints" / f"{operator}.json"

    def _atomic_write_json(self, path: Path, payload: Any) -> None:
        parent_created = not path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            self._fsync_directory(path.parent)
            if parent_created:
                self._fsync_directory(path.parent.parent)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _active_snapshot(self, run_id: str) -> tuple[dict[str, Any], Path] | None:
        run_dir = self.root / _safe_run_id(run_id)
        pointer = run_dir / "snapshot.json"
        if not pointer.exists():
            return None
        try:
            snapshot = json.loads(pointer.read_text(encoding="utf-8"))
            generation = snapshot["generation"]
            if (
                snapshot.get("schemaVersion") != 1
                or not isinstance(generation, str)
                or not _RUN_ID.fullmatch(generation)
                or not isinstance(snapshot.get("committedAt"), str)
                or not snapshot["committedAt"]
                or snapshot.get("files") != list(_SNAPSHOT_FILES)
            ):
                raise ValueError("snapshot pointer schema or generation mismatch")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise HarnessStoreError(f"Invalid harness snapshot pointer for {run_id}: {exc}") from exc
        directory = run_dir / "snapshots" / generation
        if not directory.is_dir():
            raise HarnessStoreError(f"Missing harness snapshot generation {run_id}/{generation}")
        return snapshot, directory

    def _write_jsonl_path(self, path: Path, kind: str, values: Iterable[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
        written_at = _now()
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                for value in values:
                    payload = jsonable(value)
                    record = {
                        "schemaVersion": 1,
                        "kind": kind,
                        "payloadHash": payload_hash(payload),
                        "writtenAt": written_at,
                        "payload": payload,
                    }
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            self._fsync_directory(path.parent)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _fsync_directory(self, path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _validate_operator_name(value: str) -> None:
    if not _OPERATOR_NAME.fullmatch(value):
        raise ValueError(f"Invalid harness operator name: {value!r}")


def _safe_run_id(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError(f"Invalid harness run id: {run_id!r}")
    return run_id


def _snapshot_kind(filename: str) -> str:
    try:
        return _SNAPSHOT_FILES[filename]
    except KeyError as exc:
        raise ValueError(f"Unsupported harness snapshot file: {filename}") from exc


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")
