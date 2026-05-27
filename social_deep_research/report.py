"""Report generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from social_deep_research.models import ProviderRun, SearchItem


STOPWORDS = {
    "the", "and", "for", "with", "review", "评测", "体验", "手机", "视频", "真的", "一个", "这台",
    "pro", "max", "mini", "ultra", "plus", "iphone", "apple",
}


def make_report(user_need: str, query: str, runs: list[ProviderRun], output: Path) -> str:
    items = [item for run in runs for item in run.items]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    lines.append(f"# 社媒视频 DeepResearch MVP 报告")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 用户需求：{user_need}")
    lines.append(f"- 搜索词：{query}")
    lines.append(f"- 覆盖平台：{', '.join(sorted({run.platform for run in runs}))}")
    lines.append("")

    lines.append("## 快速结论")
    if items:
        lines.extend(_conclusion(items))
    else:
        lines.append("- 没有拿到可用结果；优先检查登录状态、平台风控、关键词是否过窄。")
    lines.append("")

    lines.append("## 原始资源")
    if items:
        lines.append("| 平台 | 标题 | 作者/频道 | 时间 | 指标 | 来源 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in items:
            title = _escape(item.title[:120])
            author = _escape(item.author)
            published = _escape(item.published)
            metrics = _escape(item.compact_metrics())
            link = f"[打开]({item.url})" if item.url else ""
            lines.append(f"| {item.platform} | {title} | {author} | {published} | {metrics} | {link} |")
    else:
        lines.append("无。")
    lines.append("")

    grouped: dict[str, list[SearchItem]] = defaultdict(list)
    for item in items:
        grouped[item.platform].append(item)
    lines.append("## 平台观察")
    for platform, platform_items in grouped.items():
        lines.append(f"### {platform}")
        for item in platform_items[:5]:
            text = item.summary_text or item.title
            lines.append(f"- {item.title}：{text[:180]}")
        lines.append("")
    if not grouped:
        lines.append("- 暂无可观察结果。")
        lines.append("")

    lines.append("## 运行日志")
    lines.append("| Provider | 平台 | 成功 | 数量 | 耗时 | 备注 |")
    lines.append("| --- | --- | --- | ---: | ---: | --- |")
    for run in runs:
        note = _escape(run.note[:240]) if run.note else ""
        lines.append(f"| {run.provider} | {run.platform} | {run.ok} | {run.count} | {run.elapsed_sec:.1f}s | {note} |")
    lines.append("")

    lines.append("## MVP 限制")
    lines.append("- 默认报告基于搜索结果元数据；只有接入字幕、评论或下载抽帧后才算真正多模态分析。")
    lines.append("- 小红书、抖音、B站可能需要真实浏览器登录/CDP 授权；空结果不等于平台没有内容。")
    lines.append("- 请只做个人学习/研究、小规模查询，并遵守平台条款、robots 与版权要求。")
    text = "\n".join(lines) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return text


def _conclusion(items: list[SearchItem]) -> list[str]:
    platform_counts = Counter(item.platform for item in items)
    terms = Counter()
    for item in items:
        for token in _tokens(item.title):
            if token.lower() not in STOPWORDS and len(token) > 1:
                terms[token.lower()] += 1
    top_terms = ", ".join(term for term, _ in terms.most_common(8)) or "暂无明显高频词"
    return [
        f"- 本轮拿到 {len(items)} 条资源，平台分布：" + ", ".join(f"{k} {v}" for k, v in platform_counts.items()) + "。",
        f"- 高频主题/型号线索：{top_terms}。",
        "- 下一步应抓取单条视频的字幕、评论和关键帧，再让模型做证据归因；当前结论只能作为候选内容入口。",
    ]


def _tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text)


def _escape(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
