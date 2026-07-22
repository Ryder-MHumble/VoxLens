from __future__ import annotations

import os
import sys
from pathlib import Path


def _int_env(name: str, fallback: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(fallback))))
    except ValueError:
        return fallback


def _float_env(name: str, fallback: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(fallback))))
    except ValueError:
        return fallback


def _bool_env(name: str, fallback: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    # The script is launched with cwd=packages/crawler, so make its modules importable.
    sys.path.insert(0, str(Path.cwd()))

    import config  # type: ignore[import-not-found]
    from main import async_cleanup, main as crawler_main  # type: ignore[import-not-found]
    from tools.app_runner import run  # type: ignore[import-not-found]

    config.CRAWLER_MAX_NOTES_COUNT = _int_env("VOXLENS_MC_MAX_NOTES", config.CRAWLER_MAX_NOTES_COUNT)
    config.CRAWLER_MAX_SLEEP_SEC = _float_env("VOXLENS_MC_SLEEP_SEC", config.CRAWLER_MAX_SLEEP_SEC)
    config.ENABLE_CDP_MODE = _bool_env("VOXLENS_MC_ENABLE_CDP", True)
    config.CDP_CONNECT_EXISTING = _bool_env("VOXLENS_MC_CDP_CONNECT_EXISTING", True)
    config.CDP_REQUIRE_EXISTING_BROWSER = _bool_env("VOXLENS_MC_CDP_REQUIRE_EXISTING", True)
    config.SAVE_LOGIN_STATE = _bool_env("VOXLENS_MC_SAVE_LOGIN_STATE", True)
    config.AUTO_CLOSE_BROWSER = _bool_env("VOXLENS_MC_AUTO_CLOSE_BROWSER", False)
    config.HEADLESS = _bool_env("VOXLENS_MC_HEADLESS", False)
    config.CDP_HEADLESS = _bool_env("VOXLENS_MC_CDP_HEADLESS", False)
    config.BROWSER_LAUNCH_TIMEOUT = _int_env("VOXLENS_MC_BROWSER_LAUNCH_TIMEOUT", config.BROWSER_LAUNCH_TIMEOUT)
    if custom_browser_path := os.getenv("VOXLENS_MC_CUSTOM_BROWSER_PATH"):
        config.CUSTOM_BROWSER_PATH = custom_browser_path
    run(crawler_main, async_cleanup, cleanup_timeout_seconds=15.0)


if __name__ == "__main__":
    main()
