from __future__ import annotations

from datetime import datetime

from app.models import Comment, ResearchReport, Source

LOGOS = {
    "bilibili": "https://www.bilibili.com/favicon.ico",
    "douyin": "https://www.douyin.com/favicon.ico",
    "youtube": "https://www.youtube.com/favicon.ico",
    "xiaohongshu": "https://www.xiaohongshu.com/favicon.ico",
    "zhihu": "https://static.zhihu.com/heifetz/favicon.ico",
}

THUMBS = [
    "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1598327105666-5b89351aff97?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1565630916779-e303be97b6f5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1605236453806-6ff36851218e?auto=format&fit=crop&w=420&q=80",
]


def demo_report(lang: str = "zh", query: str = "Best camera phones under $500") -> ResearchReport:
    zh = lang == "zh"
    sources: list[Source] = []
    platforms = ["bilibili"] * 8 + ["douyin"] * 7 + ["youtube"] * 8
    titles = [
        "500美元以内拍照手机横评：Pixel 7a 仍是夜景王者",
        "iPhone SE 2022 影像体验：视频稳但续航一般",
        "小米 13T 徕卡色彩实拍，白天样张很讨喜",
        "Galaxy A54 相机样张与低光测试",
        "Nothing Phone 2a 真实一周体验",
        "Pixel 7a vs iPhone SE：人像和视频谁更稳",
        "预算机拍照避坑：别只看像素",
        "2024 中端手机影像榜单复盘",
        "500美元相机手机怎么选？抖音创作者实拍总结",
        "Pixel 7a 夜景模式挑战 iPhone SE",
        "小米 13T 街拍样张：徕卡风格适合谁",
        "A54 白天好看，夜景噪点偏多",
        "预算手机视频防抖真实测试",
        "自拍、人像、夜景一次看完",
        "Top 5 Camera Phones Under $500 in 2024",
        "$500 Budget Camera Phone Battle",
        "Pixel 7a Long Term Camera Review",
        "iPhone SE 2022 Camera Test",
        "Xiaomi 13T Camera Review & Samples",
        "Samsung A54 Camera Review",
        "Nothing Phone 2a: Camera after 30 days",
        "Best Cheap Phones for Video Creators",
        "Low-light camera ranking under $500",
    ]
    creators = ["小白测评", "影视飓风助手", "科技美学", "极客湾", "先看评测", "数码闲聊站", "差评君", "WHYLAB", "@手机摄影课", "@影像玩机", "@TechShot", "@数码小妹", "@开箱研究所", "@拍照党", "TechReviewer", "MobileTech", "MKBHD Clips", "GSMArena", "MrMobile", "Android Authority", "The Verge", "Created Labs", "PhoneArena"]
    for idx, platform in enumerate(platforms, start=1):
        comments = [
            Comment(author="viewer", text="样张比参数更有参考价值，低光和肤色差异很明显。" if zh else "Real samples matter more than specs; low-light and skin tones differ a lot."),
            Comment(author="creator-fan", text="视频防抖和收音也应该纳入购买决策。" if zh else "Video stabilization and audio should be part of the decision."),
        ]
        sources.append(Source(
            id=idx,
            platform=platform,  # type: ignore[arg-type]
            title=titles[idx - 1],
            creator=creators[idx - 1],
            url="https://www.youtube.com/watch?v=MRtg6A1f2Ko" if platform == "youtube" else ("https://www.bilibili.com/video/BV1xx411c7mD" if platform == "bilibili" else "https://www.douyin.com/video/7340000000000000000"),
            thumbnail=THUMBS[(idx - 1) % len(THUMBS)],
            duration=["8:32", "10:21", "12:45", "9:15"][idx % 4],
            published="2024-2026",
            summary=("创作者强调真实样张、夜景、人像肤色和视频稳定性，比单纯参数更能决定购买体验。" if zh else "Creators emphasize samples, night shots, skin tone and video stability over spec-sheet megapixels."),
            metrics={"views": f"{idx * 11.7:.1f}万", "comments": 128 + idx},
            comments=comments,
            transcriptPreview="Pixel 7a 的计算摄影在暗光下优势明显，但 iPhone SE 的视频质感仍很稳定。" if zh else "Pixel 7a leads in computational low-light shots, while iPhone SE remains strong in video quality.",
        ))
    from app.services.report_builder import build_report

    return build_report(
        need=("想买一台 500 美元以内拍照最稳的手机" if zh else "Find the best camera phone under $500"),
        query=query,
        lang=lang,  # type: ignore[arg-type]
        sources=sources,
        run_logs=[],
        is_demo=True,
        generated_at=datetime.now(),
    )
