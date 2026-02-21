# EigenDigest Bot 🤖

多用户每日信息摘要 Telegram Bot — 从 RSS、网页、微信公众号拉取内容，通过 LLM 生成摘要。

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
# 编辑 .env 填入配置
```

| 变量                 | 说明                                                         |
| -------------------- | ------------------------------------------------------------ |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) 获取                    |
| `ADMIN_USER_ID`      | 你的 Telegram ID（[@userinfobot](https://t.me/userinfobot)） |
| `OPENAI_API_KEY`     | OpenAI 或兼容 API Key                                        |
| `OPENAI_BASE_URL`    | API 地址                                                     |
| `LLM_MODEL`          | 模型名称                                                     |

### 3. 启动

```bash
conda activate eigendigest
python main.py
```


## 多用户系统

### 邀请制
- 管理员使用 `/invite` 生成一次性邀请码
- 好友使用 `/join <邀请码>` 加入
- 新用户加入后自动导入所有预设信息源作为基础
- 每个用户独立管理自己的信息源和推送时间

### 管理员命令

| 命令              | 说明         |
| ----------------- | ------------ |
| `/invite`         | 生成邀请码   |
| `/users`          | 查看所有用户 |
| `/kick <user_id>` | 移除用户     |

## 用户命令

### 信息源管理

| 命令                              | 说明               |
| --------------------------------- | ------------------ |
| `/add <类型> <名称> <URL> [分组]` | 添加信息源         |
| `/remove <名称>`                  | 删除               |
| `/list`                           | 查看（按分组显示） |
| `/toggle <名称>`                  | 启用/禁用          |

### 分组管理

| 命令                  | 说明             |
| --------------------- | ---------------- |
| `/presets`            | 查看可导入的预设 |
| `/import <分组名>`    | 批量导入         |
| `/groups`             | 分组概览         |
| `/togglegroup <分组>` | 整组启用/禁用    |
| `/delgroup <分组>`    | 删除整组         |

### 推送

| 命令               | 说明                     |
| ------------------ | ------------------------ |
| `/settime <HH:MM>` | 设置推送时间（北京时间） |
| `/digest`          | 立即生成摘要             |

### 内置预设

科技 · AI · 中文科技 · 财经 · 设计 · 开源

## 项目结构

```
EigenDigest_bot/
├── bot/
│   ├── handlers.py        # 命令处理（多用户 + 管理员）
│   └── scheduler.py       # 定时任务（按用户逐个推送）
├── fetchers/
│   ├── base.py            # Article 数据类
│   ├── rss_fetcher.py     # RSS 抓取
│   └── web_fetcher.py     # 网页提取
├── llm/
│   └── summarizer.py      # LLM 摘要
├── db/
│   ├── models.py          # 多用户数据库
│   └── presets.py         # 预设分组
├── config.py              # 配置
├── main.py                # 入口
└── requirements.txt
```
