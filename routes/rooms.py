from flask import Blueprint, jsonify, request
from ac_core.models import Mode, FanSpeed
from app_context import system

rooms_bp = Blueprint('rooms', __name__, url_prefix='/api/rooms')

@rooms_bp.route('/', methods=['GET'])
def get_rooms():
    """获取所有房间状态"""
    status = system.scheduler.get_all_rooms_status()
    return jsonify(status)

@rooms_bp.route('/<int:room_id>/power_on', methods=['POST'])
def power_on(room_id: int):
    """房间开机"""
    data = request.get_json(silent=True) or {}
    current_temp = float(data.get('current_temp', 25.0))
    mode_str = data.get('mode', 'COOL').upper()
    
    # 确保mode_str不为空，为空时使用默认值COOL
    if not mode_str:
        mode_str = 'COOL'
    
    mode = Mode[mode_str]
    result = system.scheduler.power_on(room_id, current_temp, mode)
    return jsonify(result)

@rooms_bp.route('/<int:room_id>/power_off', methods=['POST'])
def power_off(room_id: int):
    """房间关机"""
    result = system.scheduler.power_off(room_id)
    return jsonify(result)

@rooms_bp.route('/<int:room_id>/adjust_speed', methods=['POST'])
def adjust_speed(room_id: int):
    """调整风速"""
    data = request.get_json(silent=True) or {}
    speed_str = str(data.get('speed', 'MEDIUM')).upper()
    speed = FanSpeed[speed_str]
    result = system.scheduler.adjust_wind_speed(room_id, speed)
    return jsonify(result)

@rooms_bp.route('/<int:room_id>/adjust_temperature', methods=['POST'])
def adjust_temperature(room_id: int):
    """调整温度"""
    data = request.get_json(silent=True) or {}
    new_target_temp = float(data.get('target_temp', 25.0))
    result = system.scheduler.adjust_temperature(room_id, new_target_temp)
    return jsonify(result)

@rooms_bp.route('/<int:room_id>/request_number_service_number', methods=['GET'])
def request_number_service_number(room_id: int):
    """获取服务编号"""
    result = system.scheduler.request_number_service_number(room_id)
    return jsonify(result)

@rooms_bp.route('/<int:room_id>/request_state', methods=['GET'])
def request_state(room_id: int):
    """获取房间状态"""
    result = system.scheduler.request_state(room_id)
    return jsonify(result)

@rooms_bp.route('/status', methods=['GET'])
def get_rooms_status():
    """获取所有房间状态（用于管理员界面）"""
    status = system.scheduler.get_all_rooms_status()
    return jsonify(status)

@rooms_bp.route('/initialize', methods=['POST'])
def initialize_room():
    """初始化房间温度"""
    data = request.get_json(silent=True) or {}
    room_id = int(data.get('room_id'))
    initial_temp = float(data.get('initial_temp', 25.0))
    
    # 验证房间是否存在
    room = system.scheduler.rooms.get(room_id)
    if room is None:
        return jsonify({"error": "房间不存在"}), 404
    
    # 更新房间的初始温度和当前温度
    room.initial_temp = initial_temp
    room.current_temp = initial_temp
    
    return jsonify({
        "message": f"房间{room_id}温度已初始化为{initial_temp}℃",
        "room_id": room_id,
        "initial_temp": initial_temp
    })

@rooms_bp.route('/<int:room_id>/bill', methods=['GET'])
def get_bill(room_id: int):
    """获取房间账单"""
    bill = system.scheduler.get_bill_for_room(room_id)
    return jsonify(bill)

@rooms_bp.route('/records/clear', methods=['POST'])
def clear_all_records():
    try:
        system.clear_all_records()
        return jsonify({"message": "All records cleared successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500