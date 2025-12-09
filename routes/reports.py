from flask import Blueprint, jsonify, request
from app_context import system
import sqlite3
import os

reports_bp = Blueprint('reports', __name__, url_prefix='/api/report')

@reports_bp.route('/summary', methods=['GET'])
def summary():
    """获取系统统计汇总"""
    report = system.scheduler.get_summary_report()
    return jsonify(report)

@reports_bp.route('/summary_range', methods=['GET'])
def summary_range():
    """
    支持按时间范围查询的统计报表接口。
    请求参数（query string）：
    - start: 起始时间字符串（可选），格式建议为 YYYY-MM-DD HH:MM:SS
    - end:   结束时间字符串（可选），格式建议为 YYYY-MM-DD HH:MM:SS
    """
    start = request.args.get('start') or None
    end = request.args.get('end') or None

    summary = system.scheduler.detail_record.get_summary_range(start_time=start, end_time=end)
    return jsonify(
        {
            'start': start,
            'end': end,
            'total_energy': round(summary['total_energy'], 4),
            'total_cost': round(summary['total_cost'], 2),
        }
    )

@reports_bp.route('/comprehensive_summary', methods=['GET'])
def comprehensive_summary():
    """
    获取综合统计报表（包含空调费用和住宿费用）
    每次关机视为过了一天，住宿费用 = 房间日租金 × 关机次数
    房间费用：R1=100元/天，R2=125元/天，R3=150元/天，R4=200元/天，R5=100元/天
    """
    # 连接数据库
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hotel_ac.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 定义房间日租金
        room_rates = {1: 100, 2: 125, 3: 150, 4: 200, 5: 100}
        
        # 获取所有当前入住的房间信息
        cursor.execute("""
            SELECT room_id, guest_name, checkin_time, power_off_count
            FROM checkin_records 
            WHERE status = 'CHECKED_IN'
            ORDER BY room_id
        """)
        
        checkin_records = cursor.fetchall()
        
        # 统计各房间信息
        room_summaries = []
        total_accommodation_cost = 0
        total_ac_cost = 0
        
        for room_id, guest_name, checkin_time, power_off_count in checkin_records:
            power_off_count = power_off_count or 0
            daily_rate = room_rates.get(room_id, 100)
            
            # 计算住宿费用：按关机次数计算天数（至少算一天）
            accommodation_cost = daily_rate * max(power_off_count, 1)
            
            # 获取空调费用
            cursor.execute("""
                SELECT SUM(cost)
                FROM detail_records 
                WHERE room_id = ?
            """, (room_id,))
            
            result = cursor.fetchone()
            ac_cost = result[0] or 0
            
            # 累计总费用
            total_accommodation_cost += accommodation_cost
            total_ac_cost += ac_cost
            
            room_summaries.append({
                "room_id": room_id,
                "guest_name": guest_name,
                "checkin_time": checkin_time,
                "days": max(power_off_count, 1),
                "daily_rate": daily_rate,
                "accommodation_cost": round(accommodation_cost, 2),
                "ac_cost": round(ac_cost, 2),
                "total_cost": round(accommodation_cost + ac_cost, 2)
            })
        
        return jsonify({
            "status": "success",
            "total_accommodation_cost": round(total_accommodation_cost, 2),
            "total_ac_cost": round(total_ac_cost, 2),
            "grand_total": round(total_accommodation_cost + total_ac_cost, 2),
            "room_count": len(room_summaries),
            "rooms": room_summaries
        })
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"获取综合统计失败：{str(e)}"
        }), 500
    finally:
        conn.close()