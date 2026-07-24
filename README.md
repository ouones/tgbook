# tgbook

Agent 友好的 Telegram 书库机器人 CLI 工具。通过 Telegram 用户账号（非 Bot Token）与固定的书库机器人交互，支持**搜索图书**和**下载图书**。

## 项目定位

tgbook 是一个**非交互式、机器可读优先**的命令行工具，专为 AI Agent（如 Claude Code、Codex、Hermes）设计，而非面向终端用户的手动浏览工具。

核心设计原则：

- **每次调用只输出一行 JSON**，不掺杂日志或进度信息
- **稳定的退出码**（0-10），Agent 可据此决策重试/放弃/请求人工介入
- **零交互操作**（除 `login` 外），所有命令无需终端输入
- **会话隔离**：基于文件的 OS 级锁，同账号并发调用立即失败

## 功能

| 命令 | 说明 |
| --- | --- |
| `tgbook login` | 交互式登录，获取 Telegram 验证码并保存会话文件（仅此命令需人工操作） |
| `tgbook search "<书名>"` | 搜索书籍，返回当前页的 `/book_xxx` 命令及元数据（支持 `--page N` 翻页） |
| `tgbook download /book_xxx` | 通过搜索返回的精确命令下载书籍文件 |

### 下载幂等性

同一 `/book_xxx` 命令重复下载时，若文件已存在则直接返回 `skipped: true`，不会重复请求机器人，也不会覆盖已有文件。

### 错误码速查

| 退出码 | 错误码 | 含义 | Agent 应对策略 |
| --- | --- | --- | --- |
| 0 | - | 成功 | - |
| 1 | `internal_error` | 内部错误 | 报告给人工 |
| 2 | `invalid_input_or_config` | 输入或配置无效 | 检查参数 |
| 3 | `login_required` | 未登录或会话失效 | 停止自动化，请求人工登录 |
| 4 | `account_busy` | 另一进程正在使用此账号 | 稍后重试 |
| 5 | `no_results` | 搜索无结果 | 尝试其他查询 |
| 6 | `response_timeout` | 机器人 60 秒内未响应 | 可安全重试 |
| 7 | `protocol_error` | 机器人响应格式与预期不符 | 不要自动重试，报告人工 |
| 8 | `rate_limited` | 被限流，`retry_after` 字段含等待秒数 | 等待后重试 |
| 9 | `telegram_error` | Telegram 或网络错误 | 退避重试 |
| 10 | `download_failed` | 文件保存失败 | 检查磁盘空间和权限 |

### 输出示例

**搜索成功：**
```json
{
  "ok": true,
  "action": "search",
  "query": "遮天",
  "page": 1,
  "results": [
    {
      "command": "/book_a2RAxZLQxOL",
      "title": "遮天",
      "author": "辰东",
      "format": "epub",
      "size": "18.14 MB"
    }
  ]
}
```

**下载成功：**
```json
{
  "ok": true,
  "action": "download",
  "command": "/book_a2RAxZLQxOL",
  "path": "/data/books/遮天.epub",
  "filename": "遮天.epub",
  "format": null,
  "size": 19000000,
  "skipped": false
}
```

**错误：**
```json
{
  "ok": false,
  "error": {
    "code": "rate_limited",
    "message": "Rate limited: wait 12 seconds.",
    "retry_after": 12
  }
}
```

## 所需资源

在开始之前，你需要准备以下资源：

| # | 资源 | 用途 | 获取方式 |
|---|------|------|----------|
| 1 | **Telegram 账号** | 登录 Telegram，与机器人交互 | 在 Telegram 注册 |
| 2 | **Telegram API 凭据** (`api_id` + `api_hash`) | 通过 MTProto 协议连接 Telegram 服务器 | 访问 [my.telegram.org/apps](https://my.telegram.org/apps) 创建应用获取（见[初始化教程](#初始化教程)） |
| 3 | **个人专属 Z-Library Telegram 机器人** | 在 Telegram 中搜索和下载电子书 | 通过 @BotFather 创建后与 Z-Library 账号绑定（详见[前置条件](docs/prerequisites-zlib-telegram.md)） |
| 4 | **一台运行设备** | 部署 tgbook 并持续运行 | Linux 服务器 / NAS / Windows / **macOS** 均可 |
| 5 | **Python 3.11+** | 运行 tgbook | [python.org](https://python.org) |
| 6 | **网络环境** | 能够访问 Telegram 服务器 | 可能需要配置代理（socks5/http） |

> **提示**：步骤 1-4 只需要准备一次。项目完全支持 macOS、Linux、Windows 全平台运行。

## 环境要求

- **Python** >= 3.11
- **操作系统**：Linux（推荐）、Windows、**macOS**（全平台支持）
- **网络**：能够访问 Telegram 服务器（可能需要配置代理）

## 部署方式

### 1. 克隆仓库

```bash
git clone <repo-url> tgbook
cd tgbook
```

### 2. 安装依赖

```bash
pip install -e .
```

`tgcrypto` 需要 C 编译器才能构建。如果构建失败，pyrogram 仍可正常工作（仅速度稍慢），可跳过：

```bash
pip install kurigram==2.2.12 filelock>=3.13
pip install -e . --no-deps
```

### 3. 创建配置文件

**Linux：** 默认路径 `~/.local/share/tgbook/config.toml`（遵循 XDG 规范，可通过 `XDG_DATA_HOME` 覆盖）

**Windows：** 默认路径 `%LOCALAPPDATA%\tgbook\config.toml`

也可以使用自定义路径，通过 `--config` 参数或 `TGBOOK_CONFIG` 环境变量指定。

```toml
bot_username = "your_book_bot"
phone = "+8613800000000"
api_id = 123456
api_hash = "your-telegram-app-hash"
# proxy = "socks5://127.0.0.1:7890"  # 可选，需要代理时取消注释
```

### 4. 通过环境变量配置（可选）

所有配置项均可用环境变量覆盖，适合容器化部署：

```bash
export TGBOOK_BOT_USERNAME="your_book_bot"
export TGBOOK_PHONE="+8613800000000"
export TGBOOK_API_ID="123456"
export TGBOOK_API_HASH="your-hash"
export TGBOOK_PROXY="socks5://127.0.0.1:7890"    # 可选
export TGBOOK_CONFIG="/path/to/config.toml"        # 可选
```

### 5. 验证安装

```bash
tgbook --help
```

## 初始化教程

> **前置条件**：在开始之前，你需要先完成 [Z-Library Telegram 机器人接入](docs/prerequisites-zlib-telegram.md)，包括创建个人专属 Bot 并与 Z-Library 账号绑定。

### 第一步：获取 Telegram API 凭据（api_id 和 api_hash）

`api_id` 和 `api_hash` 是 Telegram 应用的唯一标识，用于通过 MTProto 协议连接 Telegram 服务器。

1. 在浏览器中访问 https://my.telegram.org/apps
2. 输入你的 Telegram 账号绑定的手机号（格式如 `+8613800000000`），点击「Next」
3. Telegram 会向你发送一条验证码消息，在网页中输入该验证码
4. 如果账号开启了二次验证（Two-Step Verification），按提示输入密码
5. 登录后，点击「Create an application」或选择已有的应用
6. 填写应用信息：
   - **App title**：任意名称，如 `tgbook`
   - **Short name**：任意短名，如 `tgbook`
   - **Platform**：选择 `Desktop`
   - **Description**：可选，留空即可
7. 提交后，页面会显示 `App api_id`（纯数字）和 `App api_hash`（长字符串），这两个值分别对应配置中的 `api_id` 和 `api_hash`
8. **妥善保管**这两个值，不要分享给他人

### 第二步：确认 Bot 用户名（bot_username）

`bot_username` 是你要搜索的书库机器人的 Telegram 用户名。

1. 在 Telegram 客户端中搜索该书库机器人（例如 `@your_book_bot`）
2. 进入与该机器人的私聊，发送 `/start` 确认机器人可用
3. 记住机器人的用户名（不含 `@` 符号），如 `your_book_bot`

> **注意**：你需要先在 Telegram 客户端中手动与该机器人发起对话（至少发送一条消息），否则 tgbook 无法解析到该机器人。

### 第三步：确认手机号（phone）

`phone` 是你的 Telegram 账号绑定的手机号。

- 格式为国际号码，以 `+` 开头，如 `+8613800000000`
- 该手机号必须能够接收 Telegram 的验证码短信
- 此号码就是登录 my.telegram.org 时使用的号码

### 第四步：配置代理（可选）

如果你所在的网络无法直接访问 Telegram 服务器，需要配置代理。

- 代理地址格式：`socks5://host:port` 或 `http://host:port`
- 例如：`socks5://127.0.0.1:7890`（Clash/V2Ray 等本地代理）
- 如果不需要代理，直接删除或注释掉这一行即可

### 第五步：编写配置文件

在默认路径创建 `config.toml`：

- **Linux**：`~/.local/share/tgbook/config.toml`
- **Windows**：`%LOCALAPPDATA%\tgbook\config.toml`

或者使用自定义路径，通过 `--config` 参数或 `TGBOOK_CONFIG` 环境变量指定。

```toml
bot_username = "your_book_bot"           # 替换为你的书库机器人用户名
phone = "+8613800000000"             # 替换为你的 Telegram 绑定手机号
api_id = 123456                      # 替换为 my.telegram.org 获取的 api_id
api_hash = "your-telegram-app-hash"  # 替换为 my.telegram.org 获取的 api_hash
# proxy = "socks5://127.0.0.1:7890" # 可选，需要代理时取消注释并替换地址
```

### 第六步：交互式登录

```bash
tgbook login
```

程序会提示输入 Telegram 验证码。如果账号开启了二次验证，还需输入密码。登录成功后，会话文件会保存到本地，后续命令不再需要交互。

### 第七步：测试搜索

```bash
tgbook search "三体"
```

若返回 `ok: true` 且包含 `results` 数组，说明一切正常。

### 第八步：测试下载

```bash
tgbook download /book_xxx --output ./downloads
```

将 `/book_xxx` 替换为上一步搜索结果中的 `command` 字段值。

### 第九步（可选）：运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 项目结构

```
tgbook/
├── src/tgbook/
│   ├── __init__.py
│   ├── __main__.py          # python -m tgbook 入口
│   ├── cli.py               # argparse 命令分发 & JSON 输出
│   ├── config.py            # TOML + 环境变量配置解析
│   ├── models.py            # 数据模型 & BotGateway 抽象
│   ├── errors.py            # 错误码 & 异常定义
│   ├── telegram.py          # Kurigram 网关实现
│   ├── book_bot.py          # 书库机器人协议适配层
│   ├── parser.py            # 搜索结果 & 翻页按钮解析
│   └── state.py             # 账号锁 & 下载索引
├── tests/
│   ├── fixtures/            # 测试用的机器人消息文本
│   └── test_*.py            # 26 个单元/集成测试
├── skills/tgbook-operate/   # 给 AI Agent 的操作指南
├── docs/                    # 设计文档
└── pyproject.toml
```

## AI Agent 集成

项目内置了跨 Agent 操作技能文件 `skills/tgbook-operate/SKILL.md`。Agent 运行时可加载该技能，从而了解：

- 只能通过 `tgbook login`、`tgbook search`、`tgbook download` 操作，不得绕过 CLI
- `login` 仅限人工执行
- 搜索结果中的 `command` 字段必须原样传递给 `download`
- 各种错误码的含义及应对策略

## 注意事项

### 安全

- **不要将 `config.toml` 提交到 Git**。仓库的 `.gitignore` 已排除该文件
- **不要读取、复制或传输 `.session` 文件**。该文件包含敏感凭据，等效于密码
- **不要在日志或输出中暴露** `api_hash`、`phone`、`TGBOOK_API_HASH` 等敏感字段
- 使用环境变量 `TGBOOK_API_ID` / `TGBOOK_API_HASH` 传递凭据时，注意保护 shell 历史

### 网络

- 如果在中国大陆使用，通常需要配置代理（socks5 或 http），在 `config.toml` 中设置 `proxy` 字段
- 代理格式：`socks5://host:port` 或 `http://host:port`

### 并发限制

- 同一手机号同时只能运行一个 `tgbook` 进程。第二个进程会立即收到 `account_busy` 错误
- 这是通过文件锁（filelock）实现的，进程异常退出时 OS 会自动释放锁

### 速率限制

- Telegram 对 API 调用有频率限制。遇到 `rate_limited` 时，`retry_after` 字段会告知需等待的秒数
- `tgbook` 本身不会自动重试，由调用方（Agent 或脚本）负责重试逻辑

### Linux 部署注意事项

- 配置文件默认路径为 `~/.local/share/tgbook/config.toml`（XDG 规范），可通过 `XDG_DATA_HOME` 自定义
- 如使用 systemd 等后台服务运行，建议通过环境变量传入凭据，避免在服务定义中硬编码配置文件路径
- 确保运行用户对 `data/session/` 目录有读写权限

### Bot 协议限制

- `tgbook` 仅为固定的书库机器人设计，不支持任意机器人的自定义协议
- 机器人必须通过 inline keyboard 翻页，且按钮格式须为 `(N) next »`
- 搜索结果中的 `/book_xxx` 命令格式必须匹配 `/book_[A-Za-z0-9_]+`
