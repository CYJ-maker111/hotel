from flask import Blueprint, jsonify, request
from app_context import system

time_bp = Blueprint('time', __name__, url_prefix='/api')

@time_bp.route('/tick', methods=['POST'])
def tick():
    """前进时间"""
    data = request.get_json(silent=True) or {}
    seconds = int(data.get('seconds', 60))
    system.tick(seconds)
    return jsonify({'ticked': seconds})