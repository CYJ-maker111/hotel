from flask import Blueprint, request, jsonify
import sqlite3
import os
from app_context import system

# 创建账单管理蓝图
bills_bp = Blueprint('bills', __name__, url_prefix='/api/bills')

@bills_bp.route('/<int:room_id>/detail', methods=['GET'])
def get_room_bill_detail(room_id):
    """
    获取指定房间的空调使用详单
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查询房间的详单记录
        cursor.execute("""
            SELECT id, start_time, end_time, mode, target_temp, fan_speed, 
                   cost, operation_type 
            FROM detail_records 
            WHERE room_id = ? 
            ORDER BY start_time DESC
        """, (room_id,))
        
        records = cursor.fetchall()
        
        # 转换为JSON格式
        result = []
        for record in records:
            result.append({
                "id": record[0],
                "start_time": record[1],
                "end_time": record[2],
                "mode": record[3],
                "target_temp": record[4],
                "fan_speed": record[5],
                "cost": record[6],
                "operation_type": record[7]
            })
        
        return jsonify({
            "room_id": room_id,
            "records": result,
            "total_records": len(result)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取详单失败：{str(e)}"}), 500
    finally:
        conn.close()

@bills_bp.route('/<int:room_id>/summary', methods=['GET'])
def get_room_bill_summary(room_id):
    """
    获取指定房间的账单汇总信息
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查询房间的总费用和总时长
        cursor.execute("""
            SELECT SUM(cost), SUM(julianday(end_time) - julianday(start_time)) * 86400
            FROM detail_records 
            WHERE room_id = ?
        """, (room_id,))
        
        result = cursor.fetchone()
        total_cost = result[0] or 0
        total_duration = result[1] or 0  # 总时长（秒）
        
        # 获取当前入住信息
        cursor.execute("""
            SELECT guest_name, checkin_time, checkout_time 
            FROM checkin_records 
            WHERE room_id = ? AND status = 'CHECKED_IN'
        """, (room_id,))
        
        checkin_info = cursor.fetchone()
        guest_info = {
            "guest_name": checkin_info[0] if checkin_info else "",
            "checkin_time": checkin_info[1] if checkin_info else "",
            "checkout_time": checkin_info[2] if checkin_info else ""
        }
        
        return jsonify({
            "room_id": room_id,
            "total_cost": round(total_cost, 2),
            "total_duration": round(total_duration, 2),
            "guest_info": guest_info
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取账单汇总失败：{str(e)}"}), 500
    finally:
        conn.close()

@bills_bp.route('/<int:room_id>/export', methods=['POST'])
def export_room_bill(room_id):
    """
    导出指定房间的账单
    """
    try:
        # 获取房间状态
        room_status = system.scheduler.get_room_status(room_id)
        
        # 获取详单记录
        detail_response = get_room_bill_detail(room_id)
        detail_data = detail_response.get_json()
        
        # 获取汇总信息
        summary_response = get_room_bill_summary(room_id)
        summary_data = summary_response.get_json()
        
        # 构建导出数据
        export_data = {
            "room_id": room_id,
            "current_status": room_status,
            "summary": summary_data,
            "details": detail_data["records"]
        }
        
        return jsonify({
            "status": "success",
            "message": "账单导出成功",
            "data": export_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"导出账单失败：{str(e)}"}), 500