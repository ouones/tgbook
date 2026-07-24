# Z-Library Telegram 接入前置条件

> 在配置 tgbook 之前，你需要先完成以下步骤，将 Z-Library 账号绑定到个人专属 Telegram 机器人。

---

## 一、所需账号

- **Telegram 账号**：已安装 Telegram 并正常登录（需能够访问 Telegram 服务器）
- **Z-Library 账号**：已在 Z-Library 官网（如 `singlelogin.re` 等官方入口）注册并登录

## 二、创建个人专属 Telegram 机器人

1. 打开 Telegram，搜索 **@BotFather**（蓝标认证机器人），发送 `/start`
2. 发送指令 `/newbot`
3. 输入机器人**显示名称**（随意，如 `MyBookHelper`）
4. 输入机器人**用户名**（必须以 `bot` 结尾，且不与他人重复，如 `my_secret_zlib_bot`）
5. 创建成功后，@BotFather 会返回一条 **HTTP API Token**（格式如 `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`）
   - **立即复制并保存此 Token**，关闭后无法再次查看
   - 此 Token 是机器人的唯一凭证，泄露后他人可控制你的机器人

## 三、绑定至 Z-Library 账号

1. 浏览器中登录 [Z-Library 官网](https://singlelogin.re)
2. 点击右上角头像 → **编辑个人资料**（Edit Profile）
3. 找到 **Telegram Bot** / **个人电报机器人** 设置项
4. 点击 **连接机器人** / **Try it now!**
5. 粘贴上一步保存的 HTTP API Token
6. 点击 **连接** / **Connect**，提示绑定成功即可

## 四、验证机器人可用

1. 在 Telegram 中找到你刚创建的专属机器人（搜索其用户名）
2. 点击 **开始** / **Start** 激活
3. 发送任意书名（如 `三体`），确认机器人返回搜索结果

## 五、注意事项

| 事项 | 说明 |
|------|------|
| **下载额度** | 机器人下载同样消耗 Z-Library 账号的每日配额 |
| **防封隐私** | 个人专属机器人仅自己可用，稳定性远高于公用机器人；**切勿泄露 API Token** |
| **连接失效** | 若机器人某天无响应，登录 Z-Library 网页检查机器人连接状态，重新绑定即可 |
| **官方域名** | 认准 Z-Library 官方域名（如 `singlelogin.re`），警惕钓鱼网站 |
| **需先对话** | 创建完机器人后，**务必先在 Telegram 中手动与该机器人发起对话并发送 `/start`**，否则 tgbook 无法解析到该机器人 |

---

## 关联

完成以上前置步骤后，你将获得 `bot_username`（即你创建的机器人用户名，不含 `@`）用于 tgbook 配置。
