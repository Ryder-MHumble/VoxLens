# VoxLens Crawler Runtime

This directory contains the integrated crawler runtime used by VoxLens local alpha providers. It is an internal runtime component, not a standalone crawler product and not a separate user-facing documentation site.

## Supported Runtime Scope

The VoxLens API calls this runtime through `apps/api/app/providers/crawler_runner.py` for the current alpha platform set:

- Bilibili (`bili`)
- Douyin (`dy`)
- Xiaohongshu/RedNote (`xhs`)
- Zhihu (`zhihu`)
- Kuaishou (`ks`)
- Weibo (`wb`)

Unrelated standalone docs, promotional pages, WebUI assets and Baidu/Tieba runtime paths have been removed so the package stays focused on VoxLens social-video research.

## Usage Risk

This runtime uses crawler-style collection and browser automation. Misuse can cause platform rate limits, verification challenges, IP blocking, account suspension or account bans, including on Xiaohongshu/RedNote (XHS), Douyin, Bilibili, Kuaishou, Weibo and Zhihu.

Use only for low-frequency learning, research and internal evaluation. Do not use it for mass crawling, bypassing access controls, spam, credential harvesting, collecting private or sensitive data without a lawful basis, or disrupting platform operations.

## Local Invocation

VoxLens normally invokes this package from the API runtime. Manual invocation is intended only for debugging:

```bash
uv run python main.py --platform xhs --type search --keywords "example" --save_data_option jsonl --get_comment false
```

## License

This package contains adapted third-party crawler code. Keep this file together with `LICENSE` and the repository-level `THIRD_PARTY_NOTICES.md` when redistributing copies or reviewing production/commercial use.
