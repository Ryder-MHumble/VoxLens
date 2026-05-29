from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.models import ResearchRequest
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


if __name__ == "__main__":
    unittest.main()
