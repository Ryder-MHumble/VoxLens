from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from app.models import ResearchReport, ResearchRequest, RunRecord, RunStatus
from app.utils import RUNTIME_ROOT


RUNS_ROOT = RUNTIME_ROOT / "runs" / "research"
TERMINAL_STATUSES = {"completed", "partial", "failed", "cancelled"}


class RunStore:
    def __init__(self, root: Path = RUNS_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, request: ResearchRequest) -> RunRecord:
        now = _now()
        run_id = f"run-{uuid4().hex[:12]}"
        record = RunRecord(
            runId=run_id,
            status="queued",
            request=request,
            createdAt=now,
            updatedAt=now,
            queuedAt=now,
            progress=0,
        )
        self._run_dir(run_id).mkdir(parents=True, exist_ok=True)
        self._events_path(run_id).write_text("", encoding="utf-8")
        self.write_record(record, include_report=False)
        return record

    def read_record(self, run_id: str, include_report: bool = True) -> RunRecord:
        path = self._record_path(run_id)
        if not path.exists():
            raise FileNotFoundError(run_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        record = RunRecord.model_validate(data)
        if include_report:
            report = self.read_report(run_id)
            if report:
                record.report = report
        return record

    def write_record(self, record: RunRecord, include_report: bool = False) -> None:
        data = record.model_dump(mode="json")
        if not include_report:
            data["report"] = None
        self._record_path(record.runId).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_status(self, run_id: str, status: RunStatus, *, progress: int | None = None, error: str = "") -> RunRecord:
        record = self.read_record(run_id, include_report=False)
        now = _now()
        record.status = status
        record.updatedAt = now
        if status == "running" and not record.startedAt:
            record.startedAt = now
        if status in TERMINAL_STATUSES and not record.completedAt:
            record.completedAt = now
        if progress is not None:
            record.progress = max(0, min(100, progress))
        if error:
            record.error = error
        self.write_record(record, include_report=False)
        return record

    def cancel_run(self, run_id: str, reason: str) -> dict[str, Any] | None:
        record = self.read_record(run_id, include_report=False)
        if record.status in TERMINAL_STATUSES:
            return None
        event = self.append_event(run_id, {
            "type": "error",
            "runId": run_id,
            "message": reason,
            "progress": record.progress,
        })
        self.update_status(run_id, "cancelled", progress=record.progress, error=reason)
        return event

    def cancel_non_terminal_runs(self, reason: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for record in self.iter_records(include_report=False):
            if record.status in TERMINAL_STATUSES:
                continue
            event = self.cancel_run(record.runId, reason)
            if event:
                events.append(event)
        return events

    def iter_records(self, *, include_report: bool = False) -> Iterable[RunRecord]:
        for path in sorted(self.root.glob("*/record.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = RunRecord.model_validate(data)
                if include_report:
                    report = self.read_report(record.runId)
                    if report:
                        record.report = report
                yield record
            except Exception:
                continue

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        record = self.read_record(run_id, include_report=False)
        sequence = record.eventCount + 1
        event = {"sequence": sequence, **event}
        with self._events_path(run_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(jsonable_encoder(event), ensure_ascii=False) + "\n")

        record.eventCount = sequence
        record.updatedAt = _now()
        if isinstance(event.get("progress"), int):
            record.progress = max(record.progress, min(100, int(event["progress"])))
        if event.get("type") == "run_started":
            record.status = "running"
            record.startedAt = record.startedAt or record.updatedAt
        elif event.get("type") == "final_report":
            report_payload = event.get("report")
            if report_payload:
                report = ResearchReport.model_validate(report_payload)
                self.write_report(run_id, report)
                record.status = "partial" if report.status == "partial" else "completed"
                record.progress = 100
                record.completedAt = record.updatedAt
        elif event.get("type") == "error":
            record.status = "failed"
            record.error = str(event.get("message", ""))[:500]
            record.completedAt = record.updatedAt
        self.write_record(record, include_report=False)
        return event

    def iter_events(self, run_id: str, after: int = 0) -> Iterable[dict[str, Any]]:
        path = self._events_path(run_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = json.loads(line)
                if int(event.get("sequence", 0)) > after:
                    events.append(event)
        return events

    def write_report(self, run_id: str, report: ResearchReport) -> None:
        self._report_path(run_id).write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def read_report(self, run_id: str) -> ResearchReport | None:
        path = self._report_path(run_id)
        if not path.exists():
            return None
        return ResearchReport.model_validate_json(path.read_text(encoding="utf-8"))

    def _run_dir(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / safe

    def _record_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "record.json"

    def _events_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "events.jsonl"

    def _report_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "report.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
