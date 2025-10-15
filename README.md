# Wechat Bot (企业微信推送服务)

这是一个轻量级的企业微信推送服务，使用 Flask 提供配置页面与 API，通过 APScheduler 做定时推送。项目目标是让你能够配置推送时间、频率与推送模板，并由服务器统一向企业微信 webhook 发送消息（避免浏览器直接调用 webhook 带来的 CORS/网络问题）。

## 目录结构

```
/root/wechat-bot
├─ app.py              # Flask 后端 + 调度器
├─ hello.py            # 简单示例脚本
├─ config.json         # 运行时配置（JSON 文件）
├─ ecosystem.config.js # pm2 配置（用于守护进程）
├─ README.md
├─ templates/
│  └─ index.html       # 前端界面
└─ logs/
   ├─ out.log
   └─ err.log
```

## 环境要求

- Python 3.8+（仓库中使用的是虚拟环境 `.venv`，建议使用 Python 3.11）
- 建议创建并激活虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 如果没有 requirements.txt，请安装 flask requests apscheduler
```

（此仓库不包含 requirements.txt 的话，安装以下包即可：`flask requests apscheduler jinja2`）

## 运行

开发/调试模式（快速）：

```bash
source .venv/bin/activate
python app.py
# 或指定环境变量
HOST=0.0.0.0 PORT=2029 FLASK_DEBUG=1 python app.py
```

生产：使用 pm2 守护（项目中保存了 `ecosystem.config.js`）：

```bash
# 安装 pm2（如果尚未安装）
npm install -g pm2

# 启动并保存进程
pm2 start ecosystem.config.js --env production
pm2 save
pm2 startup   # 按提示执行生成 systemd 的命令
```

pm2 配置中的 `interpreter` 指向虚拟环境内的 Python 可执行文件（例如 `/root/wechat-bot/.venv/bin/python`）。如果启动时报错类似 “source code cannot contain null bytes”，请检查 `ecosystem.config.js` 的 `script` 是否指向 Python 脚本（如 `app.py`），并把 `interpreter` 设置为 Python 二进制。

默认服务端口：2029（可通过 `PORT` 环境变量覆盖），默认监听地址 `0.0.0.0`（可用 `HOST` 环境变量覆盖）。

## 配置

主要配置保存在根目录的 `config.json`（运行时会读写此文件）。常见字段：

- `webhook_url`：企业微信 webhook 完整 URL（形如 `https://qyapi.weixin.qq.com/...&key=XXXX`）
- `push_times`：每天的推送时间数组（例如 `["08:30", "18:30"]`）
- `push_frequency`：推送频率，可选值示例：`每天`、`每周`、`每月`、`法定工作日`
- `push_template`：用于渲染推送内容的 Jinja2 模板（可在前端 UI 编辑）

示例 `config.json`：

```json
{
  "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx",
  "push_times": ["09:00"],
  "push_frequency": "每天",
  "push_template": "**{%- raw -%}你好，当前时间：{{ push_time }}。推送类型：{{ push_type }}。{%- endraw -%}",
  "total_pushes": 0
}
```

注意：`push_template` 会被 Jinja2 渲染，模板中可使用以下变量：

- `push_time`：实际推送的时间字符串（例如 `2025-10-15 09:00`）
- `push_type`：手动/自动推送类型或标题（来自前端的 `message_title`）
- `push_frequency`：配置的频率文本（例如 `每天`）
- `total_pushes`：此服务自上次重启或记录以来成功推送计数（取决于实现）

示例模板：

```
## 每日提醒
现在时间：{{ push_time }}
推送类型：{{ push_type }}
本月已推送次数：{{ total_pushes }}
```

模板渲染失败时，后端会回退到内置默认模板以保证消息能发送。

## API 列表（后端）

- GET `/api/config` — 获取当前配置（JSON）
- POST `/api/config` — 保存配置（接受 JSON，示例字段见上）
- POST `/api/push/manual` — 触发一次手动推送（body 可包含 `message_title` 或使用前端 UI）
- POST `/api/test-connection` — 后端使用给定 `webhook_url` 向企业微信发送一次测试消息（推荐用于规避浏览器直接调用 webhook 的 CORS 或网络限制）
- GET `/api/history` —（如实现）返回推送历史
- GET `/api/status` — 返回简单的运行状态

前端 UI 在 `templates/index.html`，包含“测试连接”、“立即推送”、“编辑模板”等交互。若浏览器端仍然提示“网络连接失败”，请确保前端已从服务器拉取最新的 `index.html`（尝试强制刷新 Ctrl+F5 或清除浏览器缓存），因为早期版本的前端可能直接由客户端发请求到企业微信 webhook，造成失败。

## 日志与故障排查

- pm2 日志路径：`logs/out.log`、`logs/err.log`（由 `ecosystem.config.js` 指定）
- 常见问题：
  - 无法发送：检查 `config.json` 中 `webhook_url` 是否完整、服务能否访问外网（服务器端可以直接 curl 测试）
  - 前端“网络连接失败”：说明浏览器在直接调用 `qyapi.weixin.qq.com`，请更新前端到最新版本或清缓存；也可在浏览器开发者工具 Network 面板中查看失败请求的目标 URL
  - pm2 报错“source code cannot contain null bytes”：通常是 `ecosystem.config.js` 中 `script` 指向了 Python 可执行文件（例如 `/root/wechat-bot/.venv/bin/python`），而不是脚本本身；修复方法是把 `script` 指回 `app.py` 并把 `interpreter` 设置为 Python 二进制

## 关于“法定工作日”选项

前端 UI 包含“法定工作日”选项（工作日：周一到周五，排除法定节假日）。当前后端版本会识别“工作日/周末/每天/每周/每月”等基础频率，但不包含中国法定节假日历表的自动判断。如需自动识别节假日，可：

1. 使用第三方 API（例如国家法定节假日数据）在调度前判断当天是否为法定节假日
2. 在服务内维护一份节假日白名单/黑名单并按年更新

两种方案都有优缺点：使用外部 API 更方便但依赖网络；维护本地表更稳定但需运维更新。

## 安全与注意事项

- 请勿在公开仓库中直接提交含有真实 webhook key 的 `config.json`。
- webhook URL 应保密，必要时可把其放到环境变量或加密存储中。

## 变更记录 / 维护者笔记

- 2025-10-15: 添加 Jinja2 模板渲染支持，新增 `/api/test-connection` 以避免浏览器直接访问 webhook。

如果你需要我把 README 翻译为英文、生成 `requirements.txt`、或把推送历史持久化到 SQLite，请告诉我，我可以继续实现这些改进。
