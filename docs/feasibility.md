# 可行性调研：跨社媒视频 DeepResearch

## 1. 有没有人做

有相邻产品，但没有看到一个完全等价的“个人购买决策 + 中文多平台视频 DeepResearch”开源或消费级工具。

- **社媒监听/洞察工具**：Brandwatch、Talkwalker、Sprinklr、Meltwater、Exolyt 等偏企业舆情、品牌监测、趋势分析，强在仪表盘和指标，不是面向个人的逐条证据报告。
- **视频搜索/AI 搜索工具**：Virlo 这类产品已把 TikTok、YouTube、Instagram Reels 等短视频搜索做成 AI workflow，但中文平台覆盖通常不足。
- **平台官方 API**：YouTube Data API 支持 `search.list`；TikTok 有 Research API / Display API 等，但权限、字段、配额和使用场景限制明显。
- **开源爬虫基底**：MediaCrawler 覆盖小红书、抖音、快手、B站、微博、贴吧、知乎，并已支持 CDP 真实浏览器模式，是很合适的工程基底。

## 2. 可行性判断

### 可以做的部分

- 跨平台关键词搜索：可行，B站/YouTube/小红书都已有可自动化入口；MediaCrawler 可补抖音、快手等中文平台。
- 原始链接报告：可行，先汇聚标题、作者、发布时间、点赞/播放/评论等元数据即可形成 MVP。
- 多模态分析：可行但成本更高；应分阶段做字幕/评论优先，视频关键帧和音频转写作为增强。
- 真实浏览器 Cookie：可行，MediaCrawler 当前 CDP 模式已经接近这个思路；不建议直接解密浏览器 Cookie DB，CDP/持久化浏览器上下文更稳。

### 难点

- 登录与风控：抖音/小红书/B站会变化，空结果、滑块、手机号验证都可能发生。
- 数据合规：平台条款、robots、版权、用户隐私、反爬规则都需要边界；建议只做个人低频研究。
- 语义评价质量：视频标题经常夸张或 SEO 化，必须结合评论、字幕、关键帧才能减少误判。
- 成本和延迟：跨平台下载/转写/视觉分析会让一次报告从几十秒变成数分钟，并增加 API 成本。

## 3. 推荐产品路线

1. **MVP**：跨平台搜索 + 标准化 + Markdown 报告 + 原始链接。
2. **证据增强**：抓取字幕、简介、热评；对每条候选生成“支持/反对/风险点”。
3. **多模态增强**：用 ffmpeg 抽关键帧、截取音频，再做视觉/语音摘要。
4. **研究 Agent**：自动改写关键词、去重、按可信度和相关度排序、给出最终建议。
5. **合规层**：限频、只保存必要字段、尊重登录态、可删除缓存、避免批量抓取。

## 4. MVP 取舍

本仓库实现的是第 1 步，并预留第 3 步的 ffmpeg hook。默认不下载视频，不绕过登录，不做大规模抓取。

## 5. 参考链接

- MediaCrawler: https://github.com/NanmiCoder/MediaCrawler
- MediaCrawler README English: https://github.com/NanmiCoder/MediaCrawler/blob/main/README_en.md
- MediaCrawler license: https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE
- YouTube Data API `search.list`: https://developers.google.com/youtube/v3/docs/search/list
- YouTube Data API quota costs: https://developers.google.com/youtube/v3/determine_quota_cost
- TikTok API rate limits: https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit/
- Virlo Orbit docs: https://dev.virlo.ai/docs/orbit
