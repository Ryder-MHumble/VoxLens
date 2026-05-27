# DeepResearch Runtime Contract

本文件描述 VoxLens 从用户 query 到 DeepResearch 报告的最小可用闭环，前端不要再推导核心研究状态，统一消费后端返回的数据。

## API

- `POST /api/research`：同步返回完整 `ResearchReport`，适合测试和非流式调用。
- `POST /api/research/stream`：以 SSE 格式流式返回研究过程，前端结果页默认使用此接口。
- `GET /api/demo-report`：只用于无 query 的展示，不再作为任意 query 的低质量回退。

`ResearchRequest` 现在支持 `maxParallelPlatforms` 和 `maxParallelVideos`：前者控制多平台/Provider 并发，后者控制每个平台内视频、笔记、文章等内容详情抓取并发。前端可以传 3 作为默认值，强制实时刷新时传 4。

## 流式事件

`/api/research/stream` 使用 `fetch` + `ReadableStream`，因为请求体是 POST JSON，不使用 `EventSource`。

`sources`、`outline`、`report_patch`、`section_*` 和 `final_report` 仍持续向前端流式输出；前端可以边收集来源、边显示目录、边追加报告正文。

事件顺序：

1. `run_started`：返回 `runId`、`query`、`stages`，前端创建 draft report。
2. `stage`：更新 `ui.stages`、整体 `progress`、当前阶段文案。
3. `plan`：返回 `ResearchPlan` 和 `QueryPlannerAgent` trace。
4. `provider_started`：告诉前端正在访问哪个平台/Provider。
5. `sources`：每个 Provider 完成后增量返回 `sources[]` 和 `RunLog`。
6. `agent_step`：返回爬虫、证据守卫等 Agent 的阶段性 trace。
7. `evidence`：返回排序后的来源，包含 evidence/relevance 相关字段。
8. `outline`：返回后端生成的 `outline`、`takeaways`、`insights`、`coverage`、`warnings`。
9. `report_patch`：返回不含正文 section 的报告壳，用于前端进入报告布局。
10. `section_started` / `section_delta` / `section_complete`：正文流式输出；前端追加 `delta`，完成后用完整 section 覆盖。
11. `final_report`：返回最终完整 `ResearchReport`。
12. `error`：返回失败信息，保留已收集到的阶段/来源。

## 前端模块与后端字段

### 进度模块

读取：

- `report.ui.stages[]`
- `event.progress`
- `event.message`
- `report.warnings[]`

用途：

- 显示规划、搜索、证据整理、报告生成四阶段。
- 失败时保留失败 Provider 的提示，而不是空白 loading。

### Sources 模块

读取：

- `report.sources[]`
- `source.id`
- `source.platform`
- `source.sourceType`
- `source.domain`
- `source.author`
- `source.url`
- `source.summary`
- `source.evidenceChannels[]`
- `source.quality`
- `source.provider`
- `source.evidenceScore`
- `source.relevanceScore`
- `source.citationCount`
- `source.badges[]`
- `source.highlights[]`
- `source.whyRelevant`

用途：

- 右侧来源卡片按平台筛选。
- 引用 hover/click 通过 `source.id` 高亮卡片。
- `citationCount` 让前端优先展示被报告多次引用的来源。

### 目录模块

读取：

- `report.outline[]`
- `outline.id`
- `outline.label`
- `outline.summary`
- `outline.sourceIds[]`
- `outline.citationCount`
- `outline.status`

用途：

- 左侧目录完全由后端报告结构驱动。
- 点击目录滚动到同名 section。
- 后续可以用 `sourceIds` 做“本节证据来源”预览。

### 报告正文模块

读取：

- `report.coverage`
- `report.insights[]`
- `report.takeaways[]`
- `report.sections[]`
- `section.kind`
- `section.body`
- `section.sourceIds[]`
- `section.metrics`
- `section.data`
- `section.bullets[].citations`
- `section.quote.sourceId`
- `section.table[].metrics`
- `section.table[].evidence`

用途：

- 所有引用 ID 均由后端生成。
- 通用 DeepResearch 结构用 `coverage` 描述采集覆盖，用 `insights` 承载结论/风险/共识，用 `section.sourceIds` 连接章节与证据。
- 前端只负责渲染、定位、高亮，不再自行拼接 citations。

## 回退策略

- 如果实时 Provider 全部失败，后端生成 evidence-limited report，说明失败原因和下一步，不编造事实结论。
- 如果来源数量低于 `minLiveSources`，后端标记 `status=partial` 和 `confidence=low/insufficient`，仍基于真实来源生成报告。
- 只有 `/api/demo-report` 才返回示例数据。

## 后续扩展点

- 增加持久化 run storage：按 `runId` 重新打开报告。
- 增加队列任务：长时间抓取时前端先创建 run，再订阅 stream。
- 增加 LLM/VLM synthesis：替换当前启发式 `report_builder`，但保持同一份 `ResearchReport` contract。
