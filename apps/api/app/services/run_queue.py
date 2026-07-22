from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

from fastapi import HTTPException

from app.harness import FileHarnessStore
from app.models import ResearchRequest, RunRecord
from app.services.research_stream import stream_research
from app.services.run_store import TERMINAL_STATUSES, RunStore


INTERRUPTED_RUN_MESSAGE = "Run interrupted by backend restart or shutdown. Please start a new run."


class RunManager:
    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or RunStore()
        self.harness_store = FileHarnessStore(self.store.root)
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        for event in self.store.cancel_non_terminal_runs(INTERRUPTED_RUN_MESSAGE):
            self._publish(str(event.get("runId", "")), event)
        if not self.worker or self.worker.done():
            self.worker = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        for event in self.store.cancel_non_terminal_runs(INTERRUPTED_RUN_MESSAGE):
            self._publish(str(event.get("runId", "")), event)
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def create_run(self, request: ResearchRequest) -> RunRecord:
        record = self.store.create(request)
        await self.queue.put(record.runId)
        return record

    def get_run(self, run_id: str) -> RunRecord:
        try:
            return self.store.read_record(run_id, include_report=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}") from exc

    async def stream_events(self, run_id: str) -> AsyncIterator[str]:
        record = self.get_run(run_id)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers[run_id].append(queue)
        last_sequence = 0
        try:
            for event in self.store.iter_events(run_id):
                last_sequence = max(last_sequence, int(event.get("sequence", 0)))
                yield _sse(event)
            record = self.get_run(run_id)
            if record.status in TERMINAL_STATUSES:
                return

            while True:
                event = await queue.get()
                sequence = int(event.get("sequence", 0))
                if sequence <= last_sequence:
                    continue
                last_sequence = sequence
                yield _sse(event)
                if event.get("type") in {"final_report", "error"}:
                    return
        finally:
            if queue in self.subscribers.get(run_id, []):
                self.subscribers[run_id].remove(queue)

    async def _worker_loop(self) -> None:
        while True:
            run_id = await self.queue.get()
            try:
                await asyncio.to_thread(self._execute_run, run_id)
            finally:
                self.queue.task_done()

    def _execute_run(self, run_id: str) -> None:
        try:
            record = self.store.read_record(run_id, include_report=False)
        except FileNotFoundError:
            return
        self.store.update_status(run_id, "running", progress=max(1, record.progress))
        try:
            for raw in stream_research(
                record.request,
                run_id=run_id,
                harness_store=self.harness_store,
            ):
                if self._is_terminal(run_id):
                    return
                event = _parse_sse(raw)
                if not event:
                    continue
                stored = self.store.append_event(run_id, event)
                self._publish(run_id, stored)
        except Exception as exc:  # noqa: BLE001
            event = {
                "type": "error",
                "runId": run_id,
                "message": str(exc),
                "progress": 100,
            }
            stored = self.store.append_event(run_id, event)
            self._publish(run_id, stored)
            self.store.update_status(run_id, "failed", progress=100, error=str(exc)[:500])

    def _publish(self, run_id: str, event: dict[str, Any]) -> None:
        if not self.loop:
            return
        for queue in list(self.subscribers.get(run_id, [])):
            self.loop.call_soon_threadsafe(queue.put_nowait, event)

    def _is_terminal(self, run_id: str) -> bool:
        try:
            return self.store.read_record(run_id, include_report=False).status in TERMINAL_STATUSES
        except FileNotFoundError:
            return True


def _parse_sse(raw: str) -> dict[str, Any] | None:
    data_lines = [
        line[5:].lstrip()
        for line in raw.splitlines()
        if line.startswith("data:")
    ]
    if not data_lines:
        return None
    return json.loads("\n".join(data_lines))


def _sse(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "message"))
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
