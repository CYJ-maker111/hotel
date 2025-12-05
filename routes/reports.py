from flask import Blueprint, jsonify, request
from app_context import system

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