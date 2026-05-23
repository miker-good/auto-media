# Auto-Media

全自动自媒体文字内容流水线。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

通过环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| AI_API_KEY | - | AI API 密钥（必填） |
| AI_BASE_URL | https://api.deepseek.com/v1 | AI API 地址 |
| AI_MODEL | deepseek-chat | AI 模型名 |
| MAX_PUBLISH_PER_DAY | 2 | 每天最多发布篇数 |
| CRAWL_INTERVAL_HOURS | 2 | 爬虫抓取间隔 |
| PUBLISH_HOUR_1 | 9 | 第一个发布时间（时） |
| PUBLISH_HOUR_2 | 17 | 第二个发布时间（时） |
| DB_PATH | auto_media.db | 数据库路径 |

## 使用

```bash
# 单次运行（测试用）
python main.py once

# 后台持续运行
python main.py
```

## 运行测试

```bash
python -m pytest tests/ -v
```
