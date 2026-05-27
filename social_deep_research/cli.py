"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from social_deep_research.ffmpeg_tools import version_info_json
from social_deep_research.report import make_report
from social_deep_research.searcher import run_search
from social_deep_research.utils import ROOT, slugify


def main() -> None:
    parser = argparse.ArgumentParser(prog="social-research", description="Cross-platform social video research MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    search_parser = sub.add_parser("search", help="search platforms and write a markdown report")
    search_parser.add_argument("need", help="user need, e.g. '想买一台拍照好的手机'")
    search_parser.add_argument("--query", default="", help="explicit search keywords; defaults to the need text")
    search_parser.add_argument("--platforms", default="youtube,bilibili,xiaohongshu", help="comma-separated platforms")
    search_parser.add_argument("--limit", type=int, default=5, help="results per platform")
    search_parser.add_argument("--provider-mode", choices=["hybrid", "opencli", "mediacrawler"], default="hybrid")
    search_parser.add_argument("--fallback-mediacrawler", action="store_true", help="fallback to MediaCrawler when OpenCLI returns no items")
    search_parser.add_argument("--media-crawler-dir", default=str(ROOT / "external" / "MediaCrawler"))
    search_parser.add_argument("--timeout", type=int, default=90)
    search_parser.add_argument("--output", default="", help="markdown output path")

    sub.add_parser("ffmpeg-check", help="show the ffmpeg binary used by this MVP")

    args = parser.parse_args()
    if args.command == "ffmpeg-check":
        print(version_info_json())
        return

    query = args.query or args.need
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    output = Path(args.output) if args.output else ROOT / "reports" / f"{slugify(query)}.md"
    save_root = ROOT / "runs" / "mediacrawler" / slugify(query)
    runs = run_search(
        query=query,
        platforms=platforms,
        limit=max(1, args.limit),
        provider_mode=args.provider_mode,
        fallback_mediacrawler=args.fallback_mediacrawler,
        media_crawler_dir=Path(args.media_crawler_dir),
        save_root=save_root,
        timeout=args.timeout,
    )
    make_report(args.need, query, runs, output)
    print(str(output.resolve()))


if __name__ == "__main__":
    main()
