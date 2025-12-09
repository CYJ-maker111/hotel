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
    字段：房间号、请求时间、服务开始时间、服务结束时间、服务时长（秒）、风速、当前费用、累积费用
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查询房间的详单记录（包含新字段）
        cursor.execute("""
            SELECT room_id, request_time, start_time, end_time, service_duration, 
                   fan_speed, cost, accumulated_cost, mode, target_temp, operation_type
            FROM detail_records 
            WHERE room_id = ? 
            ORDER BY start_time DESC
        """, (room_id,))
        
        records = cursor.fetchall()
        
        # 转换为JSON格式
        result = []
        for record in records:
            result.append({
                "room_id": record[0],           # 房间号
                "request_time": record[1] or record[2],  # 请求时间（若无则使用开始时间）
                "start_time": record[2],        # 服务开始时间
                "end_time": record[3],          # 服务结束时间
                "service_duration": record[4] or 0,  # 服务时长（秒）
                "fan_speed": record[5],         # 风速
                "cost": round(record[6], 2),    # 当前费用
                "accumulated_cost": round(record[7], 2),  # 累积费用
                # 额外字段
                "mode": record[8],
                "target_temp": record[9],
                "operation_type": record[10]
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

@bills_bp.route('/<int:room_id>/comprehensive', methods=['GET'])
def get_comprehensive_bill(room_id):
    """
    获取综合账单（住宿费+空调费）
    字段：房间号、入住时间、离开时间、空调总费用、住宿总费用、总计
    房间费用：R1=100元/天，R2=125元/天，R3=150元/天，R4=200元/天，R5=100元/天
    每次关机视为过了一天
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 定义房间日租金
        room_rates = {1: 100, 2: 125, 3: 150, 4: 200, 5: 100}
        daily_rate = room_rates.get(room_id, 100)
        
        # 获取入住信息
        cursor.execute("""
            SELECT guest_name, checkin_time, checkout_time, power_off_count
            FROM checkin_records 
            WHERE room_id = ? AND status = 'CHECKED_IN'
            ORDER BY checkin_time DESC
            LIMIT 1
        """, (room_id,))
        
        checkin_info = cursor.fetchone()
        
        if not checkin_info:
            return jsonify({"status": "error", "message": "房间未入住"}), 404
        
        guest_name, checkin_time, checkout_time, power_off_count = checkin_info
        power_off_count = power_off_count or 0
        
        # 计算住宿费用：按关机次数计算天数
        accommodation_cost = daily_rate * max(power_off_count, 1)  # 至少算一天
        
        # 获取空调总费用
        cursor.execute("""
            SELECT SUM(cost)
            FROM detail_records 
            WHERE room_id = ?
        """, (room_id,))
        
        result = cursor.fetchone()
        ac_total_cost = result[0] or 0
        
        # 计算总费用
        total_cost = accommodation_cost + ac_total_cost
        
        return jsonify({
            "room_id": room_id,
            "guest_name": guest_name,
            "checkin_time": checkin_time,
            "checkout_time": checkout_time or "",
            "ac_total_cost": round(ac_total_cost, 2),
            "accommodation_cost": round(accommodation_cost, 2),
            "total_cost": round(total_cost, 2),
            "power_off_count": power_off_count,
            "daily_rate": daily_rate
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取综合账单失败：{str(e)}"}), 500
    finally:
        conn.close()

@bills_bp.route('/<int:room_id>/reset', methods=['POST'])
def reset_room_cost(room_id):
    """
    重置指定房间的累计费用（清空该房间的所有详单记录）
    用于换客人时清零累计费用
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 删除该房间的所有详单记录
        cursor.execute("DELETE FROM detail_records WHERE room_id = ?", (room_id,))
        deleted_count = cursor.rowcount
        
        # 重置房间的当前费用
        room = system.scheduler.rooms.get(room_id)
        if room:
            room.cost = 0.0
        
        # 清除当前记录ID
        if room_id in system.scheduler.current_record_ids:
            del system.scheduler.current_record_ids[room_id]
        
        conn.commit()
        
        return jsonify({
            "status": "success",
            "message": f"房间{room_id}的累计费用已重置",
            "deleted_records": deleted_count
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": f"重置失败：{str(e)}"}), 500
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