# Auto-Media 全自动自媒体流水线 — 设计文档

## 概述

全自动文字内容流水线：爬取中文社区热门内容 → AI 洗稿改写 → 自动发布到头条号和百家号，赚取广告分成。后期扩展 Reddit/Hacker News 等英文源。

## 决策汇总

| 决策点 | 选择 |
|--------|------|
| 源平台（一期） | 知乎、微博、豆瓣 |
| 源平台（二期） | Reddit、Hacker News、Twitter |
| 素材格式 | 文字 |
| 自动化程度 | 全自动 |
| 发布平台 | 头条号 + 百家号 |
| 发布频率 | 每天 1-2 篇 |
| 变现方式 | 广告分成 |

## 架构

```
auto-media/
├── crawler/          # 爬虫模块
│   ├── __init__.py
│   ├── zhihu.py      # 知乎热榜
│   ├── weibo.py      # 微博热搜
│   └── douban.py     # 豆瓣热门
├── rewriter/         # AI 洗稿模块
│   ├── __init__.py
│   └── rewriter.py   # 调用大模型改写
├── publisher/        # 发布模块
│   ├── __init__.py
│   ├── toutiao.py    # 头条号发布
│   └── baijiahao.py  # 百家号发布
├── storage/          # 存储
│   ├── __init__.py
│   └── db.py         # SQLite 操作
├── scheduler.py      # 定时调度
├── config.py         # 配置（API 密钥等）
└── main.py           # 入口
```

## 数据流

```
爬虫定时拉取 → 存入 SQLite (状态=待洗稿)
       ↓
AI 洗稿     → 更新状态 (已洗稿)
       ↓
定时发布    → 每天 1-2 篇挑已洗稿的发出 → 标记 (已发布)
       ↓
记录日志    → 哪些发了、哪些失败
```

## SQLite 表结构

### articles（素材表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| source | TEXT | 来源平台 (zhihu/weibo/douban) |
| original_title | TEXT | 原标题 |
| original_content | TEXT | 原文内容 |
| original_url | TEXT | 原始链接 |
| status | TEXT | 待洗稿/已洗稿/已发布/跳过 |
| crawled_at | TIMESTAMP | 抓取时间 |
| retry_count | INTEGER | 失败重试次数 |

### publish_log（发布记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| article_id | INTEGER FK | 关联 articles.id |
| rewritten_title | TEXT | 洗稿后标题 |
| rewritten_content | TEXT | 洗稿后内容 |
| platform | TEXT | 发布平台 (toutiao/baijiahao) |
| status | TEXT | 成功/失败 |
| published_at | TIMESTAMP | 发布时间 |
| error_msg | TEXT | 失败原因 |

## 技术选型

| 模块 | 技术 | 原因 |
|------|------|------|
| 爬虫 | httpx + BeautifulSoup + parsel | 轻量，中文 HTML 解析足够 |
| 反爬 | fake-useragent + 随机延迟 | 模拟真实浏览器，降低被封 |
| AI 洗稿 | OpenAI 兼容 API（DeepSeek / 通义千问） | 千字几分钱，洗一篇几厘 |
| 存储 | SQLite（Python 内置 sqlite3） | 零配置，数据量不大足够用 |
| 定时任务 | APScheduler | Python 内置级调度，比 cron 灵活 |
| 发布 | DrissionPage 或模拟 HTTP | 头条/百家 API 可能不开放 |

## 洗稿策略

Prompt 模板：

> 以下是一篇网络文章，请在不改变核心信息的前提下做以下改写：换一个吸引人的标题、重组织段落结构、替换同义词、保持语气自然。输出严格JSON格式：{"title": "...", "content": "..."}

可配置参数：改写深度（轻度/中度/重度）、目标字数范围。AI 调用失败时降级为原文摘要。

## 错误处理

| 场景 | 处理策略 |
|------|---------|
| 爬虫失败 | 记录日志，下次重试，连续失败 3 次标记跳过 |
| 洗稿失败 | 降级为原文摘要 |
| AI API 超时/格式异常 | 降级为原文摘要，记录错误 |
| 发布失败 | 标记失败，下次优先重试，不重复发同一条 |
| 素材池空 | 跳过该轮，不报错 |
| 全局上限 | 每天最多 2 篇，超出堆积不发 |

## 测试策略

| 模块 | 测试方式 |
|------|---------|
| 爬虫 | 逐个跑，验证标题/内容/URL 字段完整性 |
| AI 洗稿 | 手动发 3 条请求验证返回格式，调好 prompt |
| 发布 | 注册号后手动发一篇验证流程 |
| 定时调度 | 本地跑完整流程，确认状态流转正常 |
| 异常恢复 | 模拟断网、API 超时，验证不崩溃且记录日志 |

## 边界条件

- 源平台改版导致 HTML 解析失败 → 记录日志，标记该平台暂停
- AI API 超时或返回格式异常 → 降级为原文摘要
- 素材池空了无新内容可发 → 跳过该轮，不报错
- 网络中断导致发布半截 → 发布前先写日志，发布后更新状态
