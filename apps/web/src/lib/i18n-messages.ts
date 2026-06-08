export type Lang = "en" | "zh";

export type Dict = Record<string, { en: string; zh: string }>;

export const dict: Dict = {
  brand: { en: "VoxLens", zh: "VoxLens" },
  nav_results: { en: "Demo result", zh: "示例报告" },
  hero_a: { en: "Research beyond text", zh: "研究，不止文字" },
  hero_b1: {
    en: "Choose a buying-advice view or a professional research view. VoxLens turns videos, comments and transcripts into ",
    zh: "先选买前咨询，或选专业品类研究。VoxLens 会把视频、评论和字幕压缩成",
  },
  hero_b2: { en: "answers with traceable evidence", zh: "带出处的答案" },
  hero_b3: { en: ".", zh: "。" },
  placeholder: {
    en: "What do you want to research across videos?",
    zh: "你想跨平台研究什么问题？",
  },
  placeholder_consumer: {
    en: "I want to buy a phone/headphones/coffee machine...",
    zh: "我想买手机/耳机/咖啡机，帮我少看测评直接判断...",
  },
  placeholder_business: {
    en: "Research this product/category with a cited report...",
    zh: "按专业模板研究这个产品/品类，并给出出处...",
  },
  searching_across: { en: "Searching across", zh: "默认覆盖" },
  suggestion_title: { en: "Try one of these", zh: "可以先试试这些问题" },
  mode_aria: { en: "Research mode", zh: "研究模式" },
  mode_consumer_eyebrow: { en: "For shoppers", zh: "C 端" },
  mode_consumer_title: { en: "Buying advice", zh: "消费购物咨询" },
  mode_consumer_desc: {
    en: "Ask like a real buyer: needs, budget, tradeoffs. No fixed business template.",
    zh: "站在用户视角提问：预算、使用场景、纠结点。不套固定 B 端模板。",
  },
  mode_consumer_note: {
    en: "Output: plain recommendation + caveats",
    zh: "输出：直接建议 + 避坑点",
  },
  mode_business_eyebrow: { en: "For teams", zh: "B 端" },
  mode_business_title: { en: "Product/category research", zh: "产品/品类研究" },
  mode_business_desc: {
    en: "Use a stable research template for market, users, competitors, risks and opportunities.",
    zh: "使用固定专业模板，覆盖市场、用户、竞品、风险与机会。",
  },
  mode_business_note: { en: "Output: cited research report", zh: "输出：带出处研究报告" },
  suggestion_consumer_title: { en: "Consumer prompts", zh: "消费咨询示例" },
  suggestion_business_title: { en: "Business research prompts", zh: "品类研究示例" },
  consumer_s1: {
    en: "I want a phone for kids and night photos, budget 4000-6000 RMB. Which one is safest?",
    zh: "我想买 4000-6000 元手机，主要拍娃和夜景，哪款最稳？",
  },
  consumer_s2: {
    en: "For commuting noise-canceling headphones under 1500 RMB, what should I buy?",
    zh: "通勤降噪耳机，预算 1500 元内，怎么选不踩坑？",
  },
  consumer_s3: {
    en: "A low-maintenance home coffee machine for beginners: which type should I choose?",
    zh: "家用咖啡机新手想少维护、少踩坑，应该选哪种？",
  },
  business_s1: {
    en: "Research China's robot vacuum category: user pain points, competitors and 2026 opportunities.",
    zh: "研究中国扫地机器人品类：用户痛点、竞品打法和 2026 机会。",
  },
  business_s2: {
    en: "Create a cited report on sugar-free tea content reputation and user demand.",
    zh: "生成无糖茶饮内容口碑和用户需求的带出处研究报告。",
  },
  business_s3: {
    en: "Analyze coffee machines on Douyin and Xiaohongshu: selling points, complaints and category openings.",
    zh: "分析咖啡机在抖音/小红书的卖点、差评和品类机会。",
  },
  s1: { en: "Best camera phones under 5000 RMB", zh: "5000 元以内拍照最稳的手机" },
  s2: { en: "Is Vision Pro worth daily use?", zh: "Vision Pro 日常使用到底值不值得？" },
  s3: { en: "Which action camera should I buy in 2026?", zh: "2026 年运动相机怎么选？" },
  s4: { en: "AeroPress vs Hario V60: which to buy?", zh: "AeroPress 和 Hario V60 该买哪个？" },
  research_title: { en: "Research Results", zh: "研究报告" },
  re_research: { en: "Deep re-run", zh: "深度重跑" },
  outline: { en: "Outline", zh: "报告大纲" },
  sources: { en: "Sources", zh: "原始来源" },
  all: { en: "All", zh: "全部" },
  videos: { en: "videos", zh: "条视频" },
  platforms: { en: "platforms", zh: "个平台" },
  comments: { en: "comments", zh: "条评论" },
  follow_up: { en: "follow-up", zh: "追问" },
  follow_up_ph: { en: "Ask a follow-up...", zh: "继续追问，比如：只看差评里提到的问题..." },
  key_takeaways: { en: "Key Takeaways", zh: "核心结论" },
  loading: { en: "Starting DeepResearch...", zh: "正在启动 DeepResearch..." },
  streaming_badge: { en: "Streaming", zh: "生成中" },
  partial_badge: { en: "Evidence-limited", zh: "证据有限" },
  demo_badge: { en: "Demo fallback", zh: "示例回退" },
  live_badge: { en: "Live report", zh: "实时报告" },
  streaming_report: {
    en: "Collecting sources and preparing the report stream...",
    zh: "正在检索来源并准备流式报告...",
  },
  empty_report: { en: "No report sections yet.", zh: "暂无报告正文。" },
  error_title: { en: "Could not load report", zh: "报告加载失败" },
  retry: { en: "Retry", zh: "重试" },
  empty: { en: "No sources yet.", zh: "暂无来源。" },
  generated_at: { en: "Generated at", zh: "生成时间" },
};
