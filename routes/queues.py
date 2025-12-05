from flask import Blueprint, jsonify
from app_context import system

queues_bp = Blueprint('queues', __name__, url_prefix='/api/queues')

@queues_bp.route('/served', methods=['GET'])
def get_served_queue():
    """
    获取当前服务队列中的所有房间
    """
    served_rooms = system.scheduler.get_served_queue()
    return jsonify({'served_rooms': served_rooms})

@queues_bp.route('/waiting', methods=['GET'])
def get_waiting_queue():
    """
    获取当前等待队列中的所有房间
    """
    waiting_rooms = system.scheduler.get_waiting_queue()
    return jsonify({'waiting_rooms': waiting_rooms})