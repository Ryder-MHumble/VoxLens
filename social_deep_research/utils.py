"""Shared subprocess and parsing helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def slugify(value: str, max_len: int = 48) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", value, flags=re.UNICODE).strip("-")
    return (value or "query")[:max_len]


def run_command(args: list[str], cwd: Path | None = None, timeout: int = 90) -> tuple[int, str, str, float]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    executable = shutil.which(args[0])
    if executable:
        args = [executable, *args[1:]]
    started = time.perf_counter()
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - started


def extract_first_json(text: str) -> Any:
    """Extract the first JSON object/array from noisy CLI output."""
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON payload found")


def read_jsonl_files(files: list[Path], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file in files:
        with file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(rows) >= limit:
                    return rows
    return rows
