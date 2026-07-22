from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.models import ResearchRequest
from app.services.report_builder import build_report
from app.services.run_queue import INTERRUPTED_RUN_MESSAGE, RunManager
from app.services.run_store import RunStore


def make_request() -> ResearchRequest:
    return ResearchRequest(
        need="iPhone comparison",
        query="iPhone comparison",
        platforms=["youtube"],
        useLiveProviders=True,
        useCrawlerRuntime=False,
        minLiveSources=1,
        lang="en",
    )


class RunManagerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_start_cancels_stale_running_run_from_previous_process(self) -> None:
        record = self.store.create(make_request())
        self.store.update_status(record.runId, "running", progress=35)

        manager = RunManager(self.store)
        await manager.start()
        try:
            updated = self.store.read_record(record.runId, include_report=False)
            events = list(self.store.iter_events(record.runId))
        finally:
            await manager.stop()

        self.assertEqual(updated.status, "cancelled")
        self.assertEqual(updated.progress, 35)
        self.assertEqual(updated.eventCount, 1)
        self.assertEqual(updated.error, INTERRUPTED_RUN_MESSAGE)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["message"], INTERRUPTED_RUN_MESSAGE)

    async def test_stop_cancels_non_terminal_runs_so_streams_finish(self) -> None:
        running = self.store.create(make_request())
        queued = self.store.create(make_request())
        self.store.update_status(running.runId, "running", progress=42)

        manager = RunManager(self.store)
        await manager.stop()

        self.assertEqual(self.store.read_record(running.runId, include_report=False).status, "cancelled")
        self.assertEqual(self.store.read_record(queued.runId, include_report=False).status, "cancelled")

        chunks: list[str] = []
        async for chunk in manager.stream_events(running.runId):
            chunks.append(chunk)

        self.assertTrue(any("event: error" in chunk for chunk in chunks))
        self.assertEqual(len(list(self.store.iter_events(running.runId))), 1)

    async def test_worker_injects_file_harness_store(self) -> None:
        record = self.store.create(make_request())
        seen = {}

        def fake_stream(request, run_id=None, harness_store=None):
            seen.update({"request": request, "run_id": run_id, "harness_store": harness_store})
            yield (
                "event: error\n"
                f'data: {{"type":"error","runId":"{run_id}","message":"stop","progress":100}}\n\n'
            )

        manager = RunManager(self.store)
        with patch("app.services.run_queue.stream_research", fake_stream):
            manager._execute_run(record.runId)

        self.assertEqual(seen["run_id"], record.runId)
        self.assertIs(seen["harness_store"], manager.harness_store)
        self.assertEqual(manager.harness_store.root, self.store.root)

    async def test_failed_report_remains_failed_in_run_record(self) -> None:
        record = self.store.create(make_request())
        report = build_report(
            need="missing evidence",
            query="missing evidence",
            lang="en",
            sources=[],
            run_logs=[],
            generated_at=datetime(2026, 7, 22, 12, 0, 0),
            run_id=record.runId,
            enable_llm_synthesis=False,
        )
        self.assertEqual(report.status, "failed")

        self.store.append_event(record.runId, {
            "type": "final_report",
            "runId": record.runId,
            "report": report.model_dump(mode="json"),
            "progress": 100,
        })

        updated = self.store.read_record(record.runId, include_report=False)
        self.assertEqual(updated.status, "failed")

    async def test_partial_and_completed_reports_keep_exact_run_status(self) -> None:
        base_report = build_report(
            need="status mapping",
            query="status mapping",
            lang="en",
            sources=[],
            run_logs=[],
            generated_at=datetime(2026, 7, 22, 12, 0, 0),
            run_id="template-run",
            enable_llm_synthesis=False,
        )

        for status in ("partial", "completed"):
            with self.subTest(status=status):
                record = self.store.create(make_request())
                report = base_report.model_copy(update={"runId": record.runId, "status": status})
                self.store.append_event(record.runId, {
                    "type": "final_report",
                    "runId": record.runId,
                    "report": report.model_dump(mode="json"),
                    "progress": 100,
                })

                updated = self.store.read_record(record.runId, include_report=False)
                self.assertEqual(updated.status, status)


if __name__ == "__main__":
    unittest.main()
