from flask import Blueprint, jsonify, request
from app_context import system
import sqlite3
import os

checkin_bp = Blueprint('checkin', __name__, url_prefix='/api/rooms')

@checkin_bp.route('/<int:room_id>/checkin', methods=['POST'])
def checkin(room_id: int):
    """
    登记入住API：记录客人信息并可选地开机
    要求：必须填写客人姓名和入住时间
    """
    data = request.get_json(silent=True) or {}
    guest_name = data.get('guest_name', '').strip()
    checkin_time = data.get('checkin_time', '').strip()
    checkout_time = data.get('checkout_time', '')
    
    # 验证必填字段
    if not guest_name:
        return jsonify({"status": "error", "message": "请填写客人姓名"}), 400
    
    if not checkin_time:
        return jsonify({"status": "error", "message": "请填写入住时间"}), 400
    
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查房间是否已被占用
        cursor.execute("SELECT * FROM checkin_records WHERE room_id = ? AND status = 'CHECKED_IN'", (room_id,))
        existing = cursor.fetchone()
        
        if existing:
            return jsonify({"status": "error", "message": f"房间 {room_id} 已被 {existing[2]} 占用"}), 400
        
        # 插入新的入住记录
        cursor.execute("INSERT INTO checkin_records (room_id, guest_name, checkin_time, checkout_time, status) VALUES (?, ?, ?, ?, 'CHECKED_IN')", 
                      (room_id, guest_name, checkin_time, checkout_time))
        conn.commit()
        
        return jsonify({
            "room_id": room_id,
            "guest_name": guest_name,
            "checkin_time": checkin_time,
            "checkout_time": checkout_time,
            "status": "success",
            "message": "登记入住成功"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"入住失败：{str(e)}"}), 500
    finally:
        conn.close()

@checkin_bp.route('/<int:room_id>/checkout', methods=['POST'])
def checkout(room_id: int):
    """
    结账API：将房间标记为已退房
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查房间是否已入住
        cursor.execute("SELECT * FROM checkin_records WHERE room_id = ? AND status = 'CHECKED_IN'", (room_id,))
        existing = cursor.fetchone()
        
        if not existing:
            return jsonify({"status": "error", "message": f"房间 {room_id} 未被占用"}), 400
        
        # 更新入住记录状态为已退房
        cursor.execute("UPDATE checkin_records SET status = 'CHECKED_OUT' WHERE room_id = ? AND status = 'CHECKED_IN'", (room_id,))
        conn.commit()
        
        return jsonify({"status": "success", "message": f"房间 {room_id} 结账成功"})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"结账失败：{str(e)}"}), 500
    finally:
        conn.close()