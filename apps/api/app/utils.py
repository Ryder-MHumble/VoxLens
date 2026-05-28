from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = REPO_ROOT / "runtime"
CRAWLER_ROOT = REPO_ROOT / "packages" / "crawler"

# Backward-compatible alias for provider modules that expect a crawler root path.
CRAWLER_DIR = CRAWLER_ROOT


def run_command(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = 90,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str, float]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    if env_extra:
        env.update(env_extra)
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


def slugify(value: str, max_len: int = 64) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", value, flags=re.UNICODE).strip("-")
    return (value or "query")[:max_len]


def bvid_from_url(value: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", value or "")
    return match.group(1) if match else value


def first_nonempty(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", text).strip()


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "results", "videos", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = rows_from_payload(value)
            if nested:
                return nested
    return []


def dedupe_sources_key(platform: str, url: str, title: str) -> str:
    if url:
        return f"{platform}:{url.lower().split('?')[0].rstrip('/')}"
    return f"{platform}:title:{strip_html(title).lower()[:120]}"


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(rows) >= limit:
                break
    return rows


def text_excerpt(parts: list[str], limit: int = 220) -> str:
    joined = " ".join(p.strip() for p in parts if p and p.strip())
    joined = re.sub(r"\s+", " ", joined)
    return joined[:limit]
