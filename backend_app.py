from flask import Flask, jsonify, request

from ac_core import HotelACSystem, FanSpeed


app = Flask(__name__, static_folder="frontend", static_url_path="/")

# 简单全局单例系统：5 间房，最多同时服务 2 间房，时间片 30 秒
system = HotelACSystem(room_count=5, capacity=2, time_slice_seconds=30)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    status = system.scheduler.get_all_rooms_status()
    return jsonify(status)


@app.route("/api/rooms/<int:room_id>/power_on", methods=["POST"])
def power_on(room_id: int):
    data = request.get_json(silent=True) or {}
    current_temp = float(data.get("current_temp", 25.0))
    result = system.scheduler.power_on(room_id, current_temp)
    return jsonify(result)


@app.route("/api/rooms/<int:room_id>/power_off", methods=["POST"])
def power_off(room_id: int):
    system.scheduler.power_off(room_id)
    return jsonify({"room_id": room_id, "state": "off"})


@app.route("/api/rooms/<int:room_id>/adjust_speed", methods=["POST"])
def adjust_speed(room_id: int):
    data = request.get_json(silent=True) or {}
    speed_str = str(data.get("speed", "MEDIUM")).upper()
    speed = FanSpeed[speed_str]
    result = system.scheduler.adjust_wind_speed(room_id, speed)
    return jsonify(result)


@app.route("/api/rooms/<int:room_id>/bill", methods=["GET"])
def get_bill(room_id: int):
    bill = system.scheduler.get_bill_for_room(room_id)
    return jsonify(bill)


@app.route("/api/report/summary", methods=["GET"])
def summary():
    report = system.scheduler.get_summary_report()
    return jsonify(report)


@app.route("/api/tick", methods=["POST"])
def tick():
    data = request.get_json(silent=True) or {}
    seconds = int(data.get("seconds", 60))
    system.tick(seconds)
    return jsonify({"ticked": seconds})


if __name__ == "__main__":
    app.run(debug=True)


