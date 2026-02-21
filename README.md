# EigenDigest Bot 🤖

每天定时从你配置的信息源（RSS、新闻网站、微信公众号）拉取内容，通过 LLM 生成摘要，发送到 Telegram。

## 快速开始

### 1. 安装依赖

```bash
conda create -n eigendigest python=3.11 -y
conda activate eigendigest
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的配置
```

| 变量                 | 说明                                                                        |
| -------------------- | --------------------------------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN` | 通过 [@BotFather](https://t.me/BotFather) 创建 Bot 获取                     |
| `ADMIN_USER_ID`      | 你的 Telegram 用户 ID（通过 [@userinfobot](https://t.me/userinfobot) 获取） |
| `OPENAI_API_KEY`     | OpenAI 或兼容 API 的 Key                                                    |
| `OPENAI_BASE_URL`    | API 地址（如 DeepSeek: `https://api.deepseek.com/v1`）                      |
| `LLM_MODEL`          | 模型名称（如 `deepseek-chat`, `gpt-4o-mini`）                               |

### 3. 启动 Bot

```bash
conda activate eigendigest
python main.py
```

## 使用方式

在 Telegram 中与 Bot 对话：

### 基础命令

| 命令                              | 说明                                     |
| --------------------------------- | ---------------------------------------- |
| `/start`                          | 欢迎信息 + 使用指南                      |
| `/add <类型> <名称> <URL> [分组]` | 添加信息源（类型: `rss`/`web`/`wechat`） |
| `/remove <名称>`                  | 删除信息源                               |
| `/list`                           | 查看所有信息源（按分组显示）             |
| `/toggle <名称>`                  | 启用/禁用信息源                          |
| `/settime <HH:MM>`                | 设置每日推送时间（北京时间）             |
| `/digest`                         | 立即生成摘要                             |
| `/help`                           | 查看帮助                                 |

### 分组管理

| 命令                    | 说明                       |
| ----------------------- | -------------------------- |
| `/presets`              | 查看可导入的预设信息源分组 |
| `/import <分组名>`      | 一键批量导入预设分组       |
| `/groups`               | 查看所有分组概览           |
| `/togglegroup <分组名>` | 启用/禁用整组              |
| `/delgroup <分组名>`    | 删除整组                   |

### 内置预设分组

| 分组     | 包含                                          |
| -------- | --------------------------------------------- |
| 科技     | HackerNews, TechCrunch, TheVerge, ArsTechnica |
| AI       | OpenAI博客, HuggingFace博客, AI新闻           |
| 中文科技 | 36氪, 少数派, 虎嗅                            |
| 财经     | 华尔街日报, Bloomberg, Reuters                |
| 设计     | Dribbble, DesignMilk                          |
| 开源     | GitHub趋势, 开源中国                          |

### 示例

```
# 一键导入预设
/import 科技
/import AI

# 手动添加（默认分组）
/add rss HackerNews https://hnrss.org/newest

# 手动添加（指定分组）
/add rss 知乎热榜 https://rsshub.app/zhihu/hotlist 中文资讯

# 微信公众号（通过 RSSHub 转 RSS）
/add rss 某公众号 https://rsshub.app/wechat/mp/xxx 公众号

# 整组管理
/togglegroup 科技
/delgroup 财经
```

> **微信公众号**: 推荐通过 [RSSHub](https://docs.rsshub.app/) 转换为 RSS 地址后使用 `rss` 类型添加。

## 项目结构

```
EigenDigest_bot/
├── bot/
│   ├── handlers.py        # Telegram 命令处理（含分组管理）
│   └── scheduler.py       # 定时任务 & 摘要流水线
├── fetchers/
│   ├── base.py            # Article 数据类 & 抽象基类
│   ├── rss_fetcher.py     # RSS/Atom 抓取
│   └── web_fetcher.py     # 网页内容提取
├── llm/
│   └── summarizer.py      # LLM 摘要生成
├── db/
│   ├── models.py          # SQLite 数据库（含分组）
│   └── presets.py         # 预设信息源分组模板
├── config.py              # 配置加载
├── main.py                # 入口
├── requirements.txt
└── .env.example
```
