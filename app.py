import json
import requests
from flask import Flask, render_template, request, jsonify
from jinja2 import Template
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import datetime
import os

app = Flask(__name__)
scheduler = BackgroundScheduler()

# --- 存储和配置 ---
CONFIG_FILE = 'config.json'
PUSH_HISTORY = [] # 存储推送历史 (最多100条)

# 初始化配置和历史记录
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "webhook_url": "",
        "push_frequency": "每日推送",  # 默认每日推送
        "push_times": ["09:00", "14:30"], # 默认时间
        "next_push_time": "未设置",
        "total_pushes": 0,
        "success_pushes": 0
    }

CONFIG = load_config()

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(CONFIG, f, indent=4)

# --- 核心推送逻辑 ---
def send_wechat_message(webhook_url, message_title, push_time):
    """向企业微信发送消息"""
    if not webhook_url:
        return False, "Webhook URL 未配置"
    # 使用用户配置的模板（Jinja2），提供上下文变量
    default_template = (
        "## 🔔 销售出勤日报提醒\n"
        "> ⏰ 推送时间: **{{ push_time }}**\n"
        "> 📅 提醒类型: **{{ push_type }}**\n"
        "> 总推送次数: **{{ total_pushes }}**\n"
        "> [点击此处查看日报详情](日报链接)"
    )

    tpl_text = CONFIG.get('push_template') or default_template
    try:
        tpl = Template(tpl_text)
        rendered = tpl.render(
            push_time=push_time,
            push_type=message_title,
            push_frequency=CONFIG.get('push_frequency'),
            total_pushes=CONFIG.get('total_pushes', 0)
        )
    except Exception as e:
        # 渲染失败则回退为默认模板文本
        rendered = default_template.format(push_time=push_time, push_type=message_title)

    data = {
        "msgtype": "markdown",
        "markdown": {"content": rendered}
    }
    
    try:
        response = requests.post(webhook_url, json=data, timeout=5)
        res_data = response.json()
        
        # 企微机器人返回 0 表示成功
        if res_data.get('errcode') == 0:
            return True, "推送成功"
        else:
            return False, f"推送失败: {res_data.get('errmsg', '未知错误')}"
    except requests.exceptions.RequestException as e:
        return False, f"网络请求失败: {e}"

def add_push_history(status, message, push_type):
    """添加推送历史记录"""
    global PUSH_HISTORY
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "time": timestamp,
        "type": push_type,
        "status": "成功" if status else "失败",
        "message": message
    }
    PUSH_HISTORY.insert(0, record)
    # 保持最多 100 条记录
    PUSH_HISTORY = PUSH_HISTORY[:100]
    
def scheduled_push_job():
    """定时任务执行的推送逻辑"""
    global CONFIG
    
    # 检查当前时间是否在推送时间列表中
    now_time_str = datetime.datetime.now().strftime("%H:%M")
    if now_time_str not in CONFIG.get('push_times', []):
        return

    # 检查是否是周推或月推
    today = datetime.date.today()
    frequency = CONFIG.get('push_frequency')
    
    if frequency == "每周推送" and today.weekday() != 0: # 0 for Monday
        return
    if frequency == "每月推送" and today.day != 1: # 1 for 1st of the month
        return

    # 执行推送
    status, message = send_wechat_message(
        CONFIG["webhook_url"],
        CONFIG["push_frequency"],
        now_time_str
    )
    
    # 更新统计数据和历史记录
    CONFIG["total_pushes"] += 1
    if status:
        CONFIG["success_pushes"] += 1
    add_push_history(status, message, "自动推送")
    save_config()


# --- 调度器设置和启动 ---
def start_scheduler():
    global scheduler, CONFIG
    
    # 移除所有现有任务
    scheduler.remove_all_jobs()
    
    frequency = CONFIG.get("push_frequency")
    
    if frequency != "关闭自动推送" and CONFIG.get("webhook_url"):
        # 添加一个每天的 Job，在 Job 内部检查时间和频率
        # 每分钟执行一次，检查是否符合推送时间点和频率要求
        scheduler.add_job(
            scheduled_push_job, 
            'interval', 
            minutes=1,
            id='auto_push_job'
        )
        
    if not scheduler.running:
        scheduler.start()
        
# --- Flask 路由 ---
@app.route('/')
def index():
    """渲染主配置页面"""
    return render_template('index.html', config=CONFIG)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """处理配置信息的获取和保存"""
    global CONFIG
    if request.method == 'GET':
        # GET 请求返回配置
        return jsonify(CONFIG)
    
    elif request.method == 'POST':
        # POST 请求保存配置
        data = request.json
        
        # 简单校验
        if not data.get('webhook_url'):
            return jsonify({"status": "error", "message": "Webhook URL 不能为空"}), 400

        CONFIG.update(data)
        
        # 清洗推送时间（移除空值并排序）
        times = [t.strip() for t in CONFIG['push_times'] if t.strip()]
        CONFIG['push_times'] = sorted(list(set(times)))
        
        save_config()
        start_scheduler() # 配置更新后重启调度器
        return jsonify({"status": "success", "message": "配置保存成功"})

@app.route('/api/push/manual', methods=['POST'])
def manual_push():
    """手动推送接口"""
    global CONFIG
    push_time = datetime.datetime.now().strftime("%H:%M")
    status, message = send_wechat_message(
        CONFIG["webhook_url"],
        "手动推送",
        push_time
    )
    
    # 更新统计数据和历史记录
    CONFIG["total_pushes"] += 1
    if status:
        CONFIG["success_pushes"] += 1
    add_push_history(status, message, "手动推送")
    save_config()
    
    return jsonify({"status": "success" if status else "error", "message": message})

@app.route('/api/history', methods=['GET'])
def get_history():
    """获取推送历史"""
    return jsonify({"history": PUSH_HISTORY})

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    total = CONFIG.get('total_pushes', 0)
    success = CONFIG.get('success_pushes', 0)
    success_rate = f"{success / total * 100:.2f}%" if total > 0 else "N/A"
    
    # 模拟计算下次推送时间 (生产环境需更严谨的调度逻辑)
    next_run = "未开启自动推送"
    if CONFIG.get("push_frequency") != "关闭自动推送":
        next_run = min(CONFIG.get("push_times"), default="未设置时间")

    return jsonify({
        "status": scheduler.running,
        "next_push_time": next_run,
        "total_pushes": total,
        "success_pushes": success,
        "success_rate": success_rate
    })


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """在服务器端向企业微信 webhook 发送一条测试消息，避免浏览器端跨域或网络限制"""
    data = request.json or {}
    webhook = data.get('webhook_url')
    if not webhook:
        return jsonify({"status": "error", "message": "Webhook URL 不能为空"}), 400

    test_payload = {
        "msgtype": "markdown",
        "markdown": {"content": "✅ **企业微信机器人连接测试成功（服务器发起）**\n> ⏰ 时间: " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    }

    try:
        resp = requests.post(webhook, json=test_payload, timeout=6)
        # 尝试解析企业微信返回的 JSON（若非 JSON 则按成功/失败判断）
        try:
            rjson = resp.json()
            if rjson.get('errcode') == 0:
                return jsonify({"status": "success", "message": "连接测试成功，企业微信返回 OK"})
            else:
                return jsonify({"status": "error", "message": f"企业微信返回错误: {rjson}"}), 502
        except ValueError:
            # 非 JSON 返回，但 HTTP 状态码 200 仍可视为成功
            if resp.status_code == 200:
                return jsonify({"status": "success", "message": "连接测试成功 (HTTP 200，非 JSON 返回)"})
            return jsonify({"status": "error", "message": f"HTTP {resp.status_code}"}), 502
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"网络请求失败: {e}"}), 502

# 在应用启动时加载配置并启动调度器
with app.app_context():
    start_scheduler()

# 在程序退出时，关闭调度器
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    # 确保保存配置在程序退出时执行
    atexit.register(save_config)
    # 运行在指定 host:port（HOST 与 PORT 可通过环境变量覆盖，默认 0.0.0.0:2029）
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 2029))
    # allow controlling debug with FLASK_DEBUG env var (default off)
    debug_env = os.environ.get('FLASK_DEBUG', 'false').lower()
    debug = debug_env in ('1', 'true', 'yes')
    app.run(host=host, port=port, debug=debug) # 生产环境请关闭 debug
