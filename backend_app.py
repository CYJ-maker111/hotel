from flask import Flask, send_from_directory
from flask_cors import CORS
import os
from routes.test import test_bp
# 初始化Flask应用
app = Flask(__name__, static_folder="frontend", static_url_path="/")

# 配置CORS，允许跨域请求（用于客户端和服务端在不同电脑）
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # 允许所有来源
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# 添加client文件夹作为静态资源目录
@app.route('/client/<path:filename>')
def serve_client(filename):
    return send_from_directory('client', filename)

# 从app_context导入系统实例
from app_context import system


@app.route("/")
def index():
    """主页路由"""
    return app.send_static_file("index.html")

# 导入并注册蓝图
from routes.rooms import rooms_bp
from routes.checkin import checkin_bp
from routes.reports import reports_bp
from routes.queues import queues_bp
from routes.time import time_bp
from routes.bills import bills_bp
from routes.db_manager import db_manager_bp

app.register_blueprint(rooms_bp)
app.register_blueprint(checkin_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(queues_bp)
app.register_blueprint(time_bp)
app.register_blueprint(bills_bp)
app.register_blueprint(db_manager_bp)
app.register_blueprint(test_bp)


if __name__ == "__main__":
    # 允许从其他电脑访问：host='0.0.0.0' 监听所有网络接口
    # 默认端口5000，可以通过环境变量PORT修改
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


