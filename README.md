# seoscout

## 本次修改说明

- **【修改位置 1】** README 的说明性文字、标题、提示、配置说明和 FAQ 已全面中文化；命令、路径、环境变量、JSON 字段与代码示例保持不变。

> **从关键词到多语言文章，一条命令完成。**

**【修改位置 2】** seoscout 是面向 SEO 从业者与内容创作者的命令行工具。输入一组关键词后，它会：

- 🔍 **搜索** YouTube（通过 yt-dlp）和 Google（通过 Serper API）
- 📥 **采集** YouTube 视频字幕与网页全文（通过 Jina Reader）
- ✍️ **生成** 由 LLM 驱动、针对 SEO 优化的 MDX 文章（包含 JS export 元数据）
- 🌍 **翻译** 文章为多种语言

无需再逐个打开搜索结果、复制粘贴内容，或购买昂贵的内容工具。

## **【修改位置 3】** 功能特性

- **完整流水线** — 关键词 → 搜索 → 采集 → 生成 → 翻译
- **并行搜索** — 同时搜索 YouTube 与 Google
- **LLM 写作** — 基于采集材料生成 SEO 文章
- **多语言** — 可翻译为任意语言（西班牙语、日语、阿拉伯语等）
- **智能过滤** — 按视频时长、主题相关性过滤，并屏蔽竞品或垃圾域名
- **缓存** — 每个来源只提取一次；再次运行会跳过已缓存内容
- **代理支持** — YouTube 字幕提取遭遇 IP 封锁时可使用轮换代理
- **可配置** — 通过 `.env` 控制并发数、批量大小和 LLM 模型

## **【修改位置 4】** 快速开始

### 前置条件

- Python 3.10+
- 已安装 [yt-dlp](https://github.com/yt-dlp/yt-dlp)（`pip install yt-dlp`）
- 一个 [Serper API](https://serper.dev/) 密钥（提供免费套餐）— 用于搜索
- 一个 [Jina AI](https://jina.ai/) API 密钥（可选，但建议配置）— 用于网页提取
- 一个 LLM API 密钥（例如通过 OpenAI 兼容端点使用 [Gemini](https://ai.google.dev/)）— 用于生成和翻译

### 安装

```bash
git clone https://github.com/Claire1940/seoscout.git
cd seoscout
pip install -e .
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API 密钥
```

### 准备关键词文件

创建包含关键词的 JSON 文件：

**分类格式**（文章会按分类存放到对应目录）：

```json
{
  "topic_name": "My Game",
  "languages": ["es", "pt", "de", "fr"],
  "categories": [
    {
      "category": "Guide",
      "keywords": [
        "My Game beginner guide",
        "My Game walkthrough",
        "My Game how to level up fast"
      ]
    },
    {
      "category": "Tier List",
      "keywords": [
        "My Game best characters tier list",
        "My Game best weapons"
      ]
    }
  ]
}
```

**扁平格式**（所有文章放在同一目录）：

```json
{
  "topic_name": "My Game",
  "keywords": [
    "My Game beginner guide",
    "My Game best characters tier list",
    "My Game tips and tricks"
  ]
}
```

> - `topic_name` 为可选项。设置后，标题或摘要中未提及该主题的搜索结果会被自动过滤。分类格式会将输出放入 `articles/en/guide/`、`articles/en/tier-list/` 等子目录。
> - `languages` 为可选项。在关键词 JSON 中设置后，`seoscout run` 会在生成文章后自动翻译为指定语言；未设置时，`seoscout translate` 必须传入 `--lang` 参数。

### 运行

```bash
# 第 1 步：在 YouTube 和 Google 搜索关键词
seoscout search --keywords keywords.json

# 第 2 步：采集字幕和网页内容
seoscout collect --keywords keywords.json

# 第 3 步：根据采集材料生成文章
seoscout generate --keywords keywords.json

# 第 4 步：翻译为其他语言
seoscout translate --keywords keywords.json --lang es,pt,de,fr
```

也可以使用一条命令完成搜索、采集和生成（若设置了 `languages`，还会翻译）：

```bash
seoscout run --keywords keywords.json
```

项目名会自动从关键词文件的 `topic_name` 推导（转为小写，并将空格替换为 `_`）。未设置 `topic_name` 时会使用文件名。

也可以作为 Python 模块运行：

```bash
python -m seoscout run --keywords keywords.json
```

## **【修改位置 5】** 工作流程

```
keywords.json
     │
     ▼
┌─────────────────────────────┐
│  seoscout search             │  ← auto project name from topic_name
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │  Google  │ │
│  │  (yt-dlp)  │ │ (Serper) │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│    search_results.json       │
│    (review & filter)         │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout collect            │
│  ┌───────────┐ ┌──────────┐ │
│  │  YouTube   │ │   Web    │ │
│  │ transcripts│ │  (Jina)  │ │
│  └─────┬─────┘ └────┬─────┘ │
│        └──────┬──────┘       │
│               ▼              │
│     collected/*.json         │
│     (per-keyword material)   │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout generate           │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│     articles/en/*.mdx        │
│     (MDX articles w/ JS      │
│      export metadata)        │
└─────────────────────────────┘
              │
              ▼
┌─────────────────────────────┐
│  seoscout translate          │
│  --lang es,pt,de,fr,ja,...  │
│        ┌──────────┐          │
│        │   LLM    │          │
│        └────┬─────┘          │
│             ▼                │
│  articles/{lang}/*.mdx       │
│  (multilingual articles)     │
└─────────────────────────────┘
```

## **【修改位置 6】** 输出格式

### search_results.json（第 1 步输出）

```json
{
  "version": "2.0",
  "created_at": "2026-06-10T12:00:00",
  "keywords": [
    {
      "keyword": "My Game beginner guide",
      "youtube": {
        "count": 2,
        "items": [
          {
            "title": "My Game Beginner Guide 2026",
            "url": "https://youtube.com/watch?v=xxx",
            "video_id": "xxx",
            "channel": "Gamer",
            "duration": "15:30",
            "duration_seconds": 930,
            "view_count": 50000,
            "selected": true
          }
        ]
      },
      "web": {
        "count": 5,
        "items": [
          {
            "title": "Complete Beginner Guide - My Game Wiki",
            "url": "https://example.com/guide",
            "domain": "example.com",
            "snippet": "Everything you need to know...",
            "selected": true
          }
        ]
      }
    }
  ]
}
```

对不需要的条目设置 `"selected": false`，然后运行 `seoscout collect`。

### collected/*.json（第 2 步输出）

每个关键词对应一个文件（例如 `my_game_beginner_guide.json`）：

```json
{
  "keyword": "My Game beginner guide",
  "collected_at": "2026-06-10T12:05:00",
  "sources": {
    "youtube": {
      "count": 1,
      "videos": [
        {
          "type": "youtube",
          "title": "My Game Beginner Guide 2026",
          "url": "https://youtube.com/watch?v=xxx",
          "content": "Full transcript text here..."
        }
      ]
    },
    "web": {
      "count": 1,
      "pages": [
        {
          "type": "web",
          "title": "Complete Beginner Guide",
          "url": "https://example.com/guide",
          "content": "Cleaned web page content here..."
        }
      ]
    }
  },
  "total_sources": 2
}
```

### articles/en/*.mdx（第 3 步输出）

每个关键词对应一个 MDX 文件（例如 `my-game-beginner-guide.mdx`）。使用 JavaScript 的 `export const metadata` 语法，以兼容 Next.js MDX wiki 项目：

```mdx
export const metadata = {
  title: "My Game Beginner Guide: Everything You Need to Know in 2026",
  description: "Complete beginner guide for My Game with tips, strategies, and walkthrough.",
  category: "guide",
  date: "2026-06-10",
}

## Getting Started

Your article content here...

## Tips and Tricks

- Tip 1...
- Tip 2...

## FAQ

**Q: Is My Game free to play?**
A: Yes, My Game is...
```

使用分类关键词时，文章会整理到 `articles/en/guide/`、`articles/en/bosses/`、`articles/en/tier-list/` 等子目录。

### articles/{lang}/*.mdx（第 4 步输出）

结构与英文文章相同，只是翻译为目标语言。任意语言代码均可使用，常见代码如下：

| 代码 | 语言 | 代码 | 语言 |
|------|----------|------|----------|
| `es` | 西班牙语 | `ko` | 韩语 |
| `pt` | 葡萄牙语（巴西） | `ru` | 俄语 |
| `de` | 德语 | `zh` | 中文 |
| `fr` | 法语 | `vi` | 越南语 |
| `ja` | 日语 | `th` | 泰语 |
| `ar` | 阿拉伯语 | `id` | 印尼语 |
| `it` | 意大利语 | `tr` | 土耳其语 |
| `pl` | 波兰语 | `nl` | 荷兰语 |
| `hi` | 印地语 | `tl` | 他加禄语 |

## **【修改位置 7】** 配置参考

所有设置均写入 `.env`（从 `.env.example` 复制后填入密钥）：

```bash
cp .env.example .env
```

### 🔑 必需项 — API 密钥

使用 seoscout 至少需要一个 API 密钥：

```bash
# 通过 Serper 搜索 Google — 必需
# 在 https://serper.dev/ 获取免费密钥
SERPER_API_KEY=your_serper_api_key_here

# 通过 Jina 提取网页内容 — 建议配置
# 未配置时可用速率限制更低
# 在 https://jina.ai/ 获取免费密钥
JINA_API_KEY=your_jina_api_key_here
```

| 变量 | 是否必需 | 获取位置 |
|----------|:--------:|--------------|
| `SERPER_API_KEY` | ✅ 是 | [serper.dev](https://serper.dev/)（提供免费套餐） |
| `JINA_API_KEY` | 建议配置 | [jina.ai](https://jina.ai/)（提供免费套餐） |
| `LLM_API_KEY` | 用于生成/翻译 | 任意 OpenAI 兼容 API（Gemini、OpenAI 等） |

### 🌐 代理 — 用于 YouTube 字幕提取

YouTube 会封锁请求字幕过于频繁的 IP。如出现 `RequestBlocked` 错误，请启用代理。

**使用轮换代理（例如青果网络 / Qingguo）：**

```bash
USE_PROXY=true
TUNNEL_HOST=overseas.tunnel.qg.net
TUNNEL_PORT=16660
TUNNEL_USER=your_username
TUNNEL_PASS=your_password
TUNNEL_PROXY_FORMAT=tagged
TUNNEL_CHANNEL_PREFIX=channel
TUNNEL_TTL=60
```

**使用标准 HTTP 代理：**

```bash
USE_PROXY=true
TUNNEL_HOST=proxy.example.com
TUNNEL_PORT=8080
TUNNEL_USER=your_username
TUNNEL_PASS=your_password
TUNNEL_PROXY_FORMAT=standard
```

**按阶段控制代理**（可选）：

```bash
# 仅在 YouTube 字幕提取时使用代理，搜索阶段不使用
USE_PROXY=false
USE_PROXY_FOR_SEARCH=false
USE_PROXY_FOR_EXTRACT=true
```

### 📁 输出

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `OUTPUT_DIR` | `./output` | 全部项目数据的根目录 |

### 🎬 YouTube 调优

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `YOUTUBE_INITIAL_SEARCH_RESULTS` | `2` | 每个关键词获取的视频数 |
| `YOUTUBE_MAX_RESULTS_AFTER_FILTER` | `1` | 过滤后保留的视频上限 |
| `YOUTUBE_MAX_DURATION` | `3600` | 跳过超过该时长（秒）的视频 |
| `YOUTUBE_EXTRACT_TOP_K` | `1` | 每个关键词要提取的字幕数 |
| `YOUTUBE_SEARCH_WORKERS` | `10` | 并行搜索工作线程数 |
| `YOUTUBE_TRANSCRIPT_WORKERS` | `15` | 并行字幕提取工作线程数 |

### 🌍 网页调优

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `WEB_SEARCH_TOP_N` | `10` | 每个关键词的 Google 结果数 |
| `WEB_EXTRACT_TOP_K` | `1` | 每个关键词要提取的网页数 |
| `WEB_SEARCH_CONCURRENCY` | `5` | Serper API 并发数 |
| `JINA_RPM` | `200` | Jina 速率限制（请求/分钟） |
| `JINA_CONCURRENCY` | `20` | Jina 并行请求数 |
| `WEB_EXTRACT_RETRIES` | `3` | 网页提取重试次数 |

### 🤖 LLM — 用于生成和翻译

`seoscout generate` 和 `seoscout translate` 必需。任意 OpenAI 兼容 API 端点均可使用（Gemini、OpenAI、DeepSeek 等）。

```bash
LLM_API_KEY=your_api_key
LLM_API_BASE_URL=https://api.apifast.tech/v1
LLM_MODEL=gemini-2.5-flash
LLM_MAX_TOKENS=24576
```

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `LLM_API_KEY` | _（空）_ | LLM 的 API 密钥 |
| `LLM_API_BASE_URL` | `https://api.apifast.tech/v1` | OpenAI 兼容端点 |
| `LLM_MODEL` | `gemini-2.5-flash` | 模型名称 |
| `LLM_TEMPERATURE` | `0.7` | 采样温度 |
| `LLM_MAX_TOKENS` | `24576` | 单次请求最大输出 token 数 |
| `LLM_TIMEOUT` | `300` | 请求超时时间（秒） |
| `LLM_RETRY_ATTEMPTS` | `2` | 失败时的重试次数 |
| `LLM_RETRY_DELAY` | `5` | 两次重试间隔（秒） |

### ⚡ 并发 — 生成和翻译

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `GENERATE_BATCH_SIZE` | `100` | 每个并行批次的文章数 |
| `GENERATE_CONCURRENT_LIMIT` | `10` | 生成请求最大并发数 |
| `TRANSLATE_BATCH_SIZE` | `10` | 每个翻译批次的文章数 |
| `TRANSLATE_BATCH_DELAY` | `1` | 翻译批次间隔（秒） |

### ⚙️ 通用设置

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `SEARCH_MAX_RETRIES` | `3` | 搜索重试次数 |
| `SEARCH_RETRY_DELAY` | `2` | 两次重试间隔（秒） |
| `BLOCKED_DOMAINS` | `youtube.com,youtu.be,...` | 从网页结果中排除的域名 |

## **【修改位置 8】** 常见问题

### 找不到 yt-dlp

请确认 yt-dlp 已安装且位于 PATH 中：

```bash
pip install yt-dlp
yt-dlp --version
```

### YouTube 字幕提取失败

YouTube 有时会封锁请求过多的 IP。可尝试：
1. 等待几分钟后重试。
2. 在 `.env` 中启用轮换代理服务。
3. 降低 `YOUTUBE_TRANSCRIPT_WORKERS` 以减少并发。

### Serper API 返回错误

- 检查 API 密钥是否正确。
- 免费套餐有速率限制；请降低 `WEB_SEARCH_CONCURRENCY`。
- 在 [serper.dev](https://serper.dev/) 查看账户余额。

### 网页内容过短或为空

某些网页会阻止自动提取。可尝试：
- 降低 `JINA_CONCURRENCY` 以避免触发速率限制。
- 添加 `JINA_API_KEY` 以提高速率限制。

### LLM 生成失败或返回为空

- 检查 `LLM_API_KEY` 是否已设置且有效。
- 如触发速率限制，尝试降低 `GENERATE_BATCH_SIZE` 或 `GENERATE_CONCURRENT_LIMIT`。
- 检查 `LLM_MAX_TOKENS`；部分模型的上限较低。
- 查看 API 服务商的状态页面。

### 如何使用自定义提示词模板？

向 `generate` 或 `translate` 传入 `--prompt /path/to/your/prompt.md`。生成模板使用 `{merged_data}`、`{current_date}` 和 `{category}` 变量；翻译模板使用 `$language_name`、`$lang_code` 和 `$content` 变量。

### 可以使用 OpenAI、DeepSeek 或其他模型吗？

可以。seoscout 使用 OpenAI 兼容的 Chat Completions API。将 `LLM_API_BASE_URL` 和 `LLM_MODEL` 设置为与你的服务商相匹配的值：

```bash
# OpenAI
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# DeepSeek
LLM_API_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

## **【修改位置 9】** 许可证

[MIT](LICENSE)
