module.exports = {
  apps : [
    {
      name: "wechat-bot",
      script: "/root/wechat-bot/app.py",
      interpreter: "/root/wechat-bot/.venv/bin/python",
      cwd: "/root/wechat-bot",
      env: {
        HOST: "0.0.0.0",
        PORT: "2029",
        FLASK_DEBUG: "false"
      },
      autorestart: true,
      watch: false,
      max_restarts: 10,
      error_file: "/root/wechat-bot/logs/err.log",
      out_file: "/root/wechat-bot/logs/out.log",
      log_date_format: "YYYY-MM-DD HH:mm Z"
    }
  ]
}
