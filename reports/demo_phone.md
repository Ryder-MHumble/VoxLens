# 社媒视频 DeepResearch MVP 报告

- 生成时间：2026-05-25 22:31
- 用户需求：我想买 iPhone 16 Pro，需要看真实评测
- 搜索词：iPhone 16 Pro review
- 覆盖平台：bilibili, xiaohongshu, youtube

## 快速结论
- 本轮拿到 2 条资源，平台分布：youtube 2。
- 高频主题/型号线索：16, times, have, changed, day, honest。
- 下一步应抓取单条视频的字幕、评论和关键帧，再让模型做证据归因；当前结论只能作为候选内容入口。

## 原始资源
| 平台 | 标题 | 作者/频道 | 时间 | 指标 | 来源 |
| --- | --- | --- | --- | --- | --- |
| youtube | iPhone 16/16 Pro Review: Times Have Changed! | Marques Brownlee | 1年前 | views: 7,718,269次观看 | [打开](https://www.youtube.com/watch?v=MRtg6A1f2Ko) |
| youtube | iPhone 16 Pro – 7 Day HONEST Review | Andrew Ethan Zeng | 1年前 | views: 510,785次观看 | [打开](https://www.youtube.com/watch?v=F7_Wi-soS3E) |

## 平台观察
### youtube
- iPhone 16/16 Pro Review: Times Have Changed!：iPhone 16/16 Pro Review: Times Have Changed!
- iPhone 16 Pro – 7 Day HONEST Review：iPhone 16 Pro – 7 Day HONEST Review

## 运行日志
| Provider | 平台 | 成功 | 数量 | 耗时 | 备注 |
| --- | --- | --- | ---: | ---: | --- |
| opencli | youtube | True | 2 | 16.3s |  |
| opencli | bilibili | True | 0 | 7.0s | no results returned; login/cookie/search quality may be the cause |
| opencli | xiaohongshu | True | 0 | 35.6s | no results returned; login/cookie/search quality may be the cause |

## MVP 限制
- 默认报告基于搜索结果元数据；只有接入字幕、评论或下载抽帧后才算真正多模态分析。
- 小红书、抖音、B站可能需要真实浏览器登录/CDP 授权；空结果不等于平台没有内容。
- 请只做个人学习/研究、小规模查询，并遵守平台条款、robots 与版权要求。
