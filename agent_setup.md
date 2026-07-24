# tgbook Agent 自动部署指南

> 本文档面向 **AI Agent**，指导其自动完成 tgbook 的安装、配置和初始化，仅最后一步 `tgbook login` 需要用户手动操作。

---

## 概述

tgbook 是一个通过 Telegram 用户账号与书库机器人交互的 CLI 工具，支持搜索和下载电子书。你需要引导用户提供配置参数，完成部署后让用户执行 `tgbook login`。

## 部署步骤

### 步骤 1：环境检查

检查当前环境是否满足要求：

- **Python** >= 3.11（运行 `python --version` 或 `python3 --version`）
- **Git**（运行 `git --version`）
- 如不满足，引导用户先安装

### 步骤 2：克隆仓库

```bash
git clone https://github.com/ouones/tgbook.git
cd tgbook
```

### 步骤 3：安装依赖

```bash
pip install -e .
```

> 如果 `tgcrypto` 构建失败（需要 C 编译器），可跳过：
> ```bash
> pip install kurigram==2.2.12 filelock>=3.13
> pip install -e . --no-deps
> ```

### 步骤 4：引导用户提供配置参数

你需要逐一询问用户以下参数。**一次只问一个**，用户提供后再问下一个。

| 参数 | 说明 | 示例 |
|------|------|------|
| `bot_username` | 用户创建的 Z-Library 专属机器人用户名（不含 `@`） | `my_zlib_bot` |
| `phone` | Telegram 账号绑定的手机号（含国际区号） | `+8613800000000` |
| `api_id` | 从 my.telegram.org/apps 获取的数字 | `123456` |
| `api_hash` | 从 my.telegram.org/apps 获取的字符串 | `abc123def456` |
| `proxy`（可选） | 代理地址，仅在中国大陆等需要代理的环境询问 | `socks5://127.0.0.1:7890` |

**交互方式：**

1. 先问 `bot_username`
2. 再问 `phone`
3. 再问 `api_id`
4. 再问 `api_hash`
5. 最后问是否需要配置代理（如用户不需要，跳过此项）

### 步骤 5：写入配置文件

根据用户提供的参数，写入配置文件。

**Linux/macOS：** `~/.local/share/tgbook/config.toml`
**Windows：** `%LOCALAPPDATA%\tgbook\config.toml`

> 确保 `data/` 目录与配置文件在同一级。

配置文件内容示例：

```toml
bot_username = "my_zlib_bot"
phone = "+8613800000000"
api_id = 123456
api_hash = "abc123def456"
# proxy = "socks5://127.0.0.1:7890"  # 用户提供了代理才写入
```

### 步骤 6：验证安装

```bash
tgbook --help
```

确认命令可正常运行，输出包含 `login`、`search`、`download` 子命令。

### 步骤 7：引导用户手动登录

tgbook 不再继续自动执行。请告知用户：

> 部署完成！现在请在终端中手动执行以下命令完成 Telegram 登录：
>
> ```bash
> tgbook login
> ```
>
> 程序会提示输入 Telegram 验证码。如果账号开启了二次验证，还需输入密码。
> 登录成功后即可使用 `tgbook search` 和 `tgbook download` 命令。

---

## 注意事项

- **不要**尝试绕过 CLI 直接操作 Telegram API
- **不要**读取、复制或传输 `.session` 文件（包含敏感凭据）
- **不要**将 `config.toml` 提交到 Git
- 如果用户需要重新配置，可以重新运行本流程
