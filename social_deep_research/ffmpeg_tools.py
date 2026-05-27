"""ffmpeg helpers for future multimodal sampling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def resolve_ffmpeg() -> str | None:
    explicit = os.environ.get("FFMPEG_BINARY")
    if explicit and Path(explicit).exists():
        return explicit
    from_path = shutil.which("ffmpeg")
    if from_path:
        return from_path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def version_info() -> dict[str, Any]:
    binary = resolve_ffmpeg()
    if not binary:
        return {"ok": False, "binary": None, "version": "ffmpeg not found"}
    proc = subprocess.run([binary, "-version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    first_line = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
    return {"ok": proc.returncode == 0, "binary": binary, "version": first_line}


def extract_keyframes(input_media: str, output_dir: Path, every_seconds: int = 10, max_frames: int = 6) -> list[Path]:
    binary = resolve_ffmpeg()
    if not binary:
        raise RuntimeError("ffmpeg not available; install ffmpeg or keep imageio-ffmpeg dependency")
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%03d.jpg"
    vf = f"fps=1/{max(1, every_seconds)}"
    command = [binary, "-y", "-i", input_media, "-vf", vf, "-frames:v", str(max_frames), str(pattern)]
    subprocess.run(command, check=True)
    return sorted(output_dir.glob("frame_*.jpg"))


def version_info_json() -> str:
    return json.dumps(version_info(), ensure_ascii=False, indent=2)
