from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.providers import crawler_provider


class CrawlerBrowserRuntimeTests(unittest.TestCase):
    def test_auto_auth_defaults_to_local_persistent_cdp_browser(self) -> None:
        captured: dict[str, object] = {}

        def fake_run_command(args, cwd=None, timeout=90, env_extra=None):
            captured["args"] = args
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            captured["env_extra"] = dict(env_extra or {})
            return 0, "", "", 0.1

        with tempfile.TemporaryDirectory() as tmp:
            crawler_root = Path(tmp)
            (crawler_root / "main.py").write_text("", encoding="utf-8")
            with (
                patch.object(crawler_provider, "CRAWLER_ROOT", crawler_root),
                patch.object(crawler_provider, "RUNTIME_ROOT", Path(tmp) / "runtime"),
                patch.object(crawler_provider, "run_command", side_effect=fake_run_command),
            ):
                crawler_provider.search_douyin(
                    "noise cancelling headphones",
                    limit=1,
                    comments_limit=0,
                    use_crawler_runtime=True,
                    auth_mode="auto",
                    video_parallelism=1,
                )

        env = captured["env_extra"]
        self.assertEqual(env["VOXLENS_MC_ENABLE_CDP"], "1")
        self.assertEqual(env["VOXLENS_MC_CDP_CONNECT_EXISTING"], "1")
        self.assertEqual(env["VOXLENS_MC_CDP_REQUIRE_EXISTING"], "1")
        self.assertEqual(env["VOXLENS_MC_SAVE_LOGIN_STATE"], "1")
        self.assertEqual(env["VOXLENS_MC_AUTO_CLOSE_BROWSER"], "0")
        self.assertEqual(env["VOXLENS_MC_HEADLESS"], "0")
        self.assertEqual(env["VOXLENS_MC_CDP_HEADLESS"], "0")


if __name__ == "__main__":
    unittest.main()
