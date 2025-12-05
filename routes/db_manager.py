from flask import Blueprint, request, jsonify
import sqlite3
import os
from datetime import datetime

# 创建蓝图
db_manager_bp = Blueprint('db_manager', __name__, url_prefix='/api/db')

# 数据库路径
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../hotel_ac.db')

# 连接数据库
def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# 获取空调使用记录
@db_manager_bp.route('/detail_records', methods=['GET'])
def get_detail_records():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取查询参数
        room_id = request.args.get('room_id')
        date = request.args.get('date')

        query = 'SELECT id, room_id, start_time, end_time, mode, target_temp, fan_speed, fee_rate, cost, operation_type FROM detail_records WHERE 1=1'
        params = []

        if room_id:
            query += ' AND room_id = ?'
            params.append(room_id)
        if date:
            query += ' AND start_time LIKE ?'
            params.append(f'{date}%')

        query += ' ORDER BY id DESC'

        cursor.execute(query, params)
        records = cursor.fetchall()
        conn.close()

        # 转换为字典列表
        records_list = []
        for record in records:
            record_dict = dict(record)
            records_list.append(record_dict)

        return jsonify(records_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 获取入住记录
@db_manager_bp.route('/checkin_records', methods=['GET'])
def get_checkin_records():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取查询参数
        room_id = request.args.get('room_id')
        guest_name = request.args.get('guest_name')

        query = 'SELECT * FROM checkin_records WHERE 1=1'
        params = []

        if room_id:
            query += ' AND room_id = ?'
            params.append(room_id)
        if guest_name:
            query += ' AND guest_name LIKE ?'
            params.append(f'%{guest_name}%')

        query += ' ORDER BY id DESC'

        cursor.execute(query, params)
        records = cursor.fetchall()
        conn.close()

        # 转换为字典列表
        records_list = []
        for record in records:
            record_dict = dict(record)
            records_list.append(record_dict)

        return jsonify(records_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 获取单个记录
@db_manager_bp.route('/<table_name>/<int:id>', methods=['GET'])
def get_record(table_name, id):
    try:
        # 验证表名
        valid_tables = ['detail_records', 'checkin_records']
        if table_name not in valid_tables:
            return jsonify({'error': 'Invalid table name'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT * FROM {table_name} WHERE id = ?', (id,))
        record = cursor.fetchone()
        conn.close()

        if record is None:
            return jsonify({'error': 'Record not found'}), 404

        record_dict = dict(record)
        # 如果是detail_records表，移除不存在的energy_used字段
        if table_name == 'detail_records':
            record_dict.pop('energy_used', None)
        # 转换日期时间格式为datetime-local兼容格式
        for key, value in record_dict.items():
            if key.endswith('_time') and value:
                try:
                    # 解析SQLite datetime格式
                    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    # 转换为datetime-local格式
                    record_dict[key] = dt.strftime('%Y-%m-%dT%H:%M')
                except ValueError:
                    pass

        return jsonify(record_dict), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 更新记录
@db_manager_bp.route('/<table_name>/<int:id>', methods=['PUT'])
def update_record(table_name, id):
    try:
        # 验证表名
        valid_tables = ['detail_records', 'checkin_records']
        if table_name not in valid_tables:
            return jsonify({'error': 'Invalid table name'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # 移除id和空值
        data.pop('id', None)
        # 如果是detail_records表，移除不存在的energy_used字段
        if table_name == 'detail_records':
            data.pop('energy_used', None)
        data = {k: v for k, v in data.items() if v is not None}

        if not data:
            return jsonify({'error': 'No valid data provided'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查记录是否存在
        cursor.execute(f'SELECT id FROM {table_name} WHERE id = ?', (id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Record not found'}), 404

        # 构建更新语句
        set_clause = ', '.join([f'{key} = ?' for key in data.keys()])
        params = list(data.values()) + [id]

        cursor.execute(f'UPDATE {table_name} SET {set_clause} WHERE id = ?', params)
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 删除记录
@db_manager_bp.route('/<table_name>/<int:id>', methods=['DELETE'])
def delete_record(table_name, id):
    try:
        # 验证表名
        valid_tables = ['detail_records', 'checkin_records']
        if table_name not in valid_tables:
            return jsonify({'error': 'Invalid table name'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查记录是否存在
        cursor.execute(f'SELECT id FROM {table_name} WHERE id = ?', (id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Record not found'}), 404

        # 删除记录
        cursor.execute(f'DELETE FROM {table_name} WHERE id = ?', (id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 批量删除记录（按条件）
@db_manager_bp.route('/<table_name>/batch_delete', methods=['POST'])
def batch_delete_records(table_name):
    try:
        # 验证表名
        valid_tables = ['detail_records', 'checkin_records']
        if table_name not in valid_tables:
            return jsonify({'error': 'Invalid table name'}), 400

        data = request.get_json()
        if not data or 'conditions' not in data:
            return jsonify({'error': 'No conditions provided'}), 400

        conditions = data['conditions']

        conn = get_db_connection()
        cursor = conn.cursor()

        # 构建删除语句
        query = f'DELETE FROM {table_name} WHERE 1=1'
        params = []

        for key, value in conditions.items():
            if value:
                if table_name == 'detail_records' and key == 'date':
                    query += f' AND {key} LIKE ?'
                    params.append(f'{value}%')
                elif table_name == 'checkin_records' and key == 'guest_name':
                    query += f' AND {key} LIKE ?'
                    params.append(f'%{value}%')
                else:
                    query += f' AND {key} = ?'
                    params.append(value)

        cursor.execute(query, params)
        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'affected_rows': affected_rows}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 清除整个表内容
@db_manager_bp.route('/detail_records', methods=['DELETE'])
def clear_detail_records():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 清除表内容
        cursor.execute('DELETE FROM detail_records')
        # 重置自增ID
        cursor.execute('DELETE FROM sqlite_sequence WHERE name = ?', ('detail_records',))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 清除整个表内容
@db_manager_bp.route('/checkin_records', methods=['DELETE'])
def clear_checkin_records():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 清除表内容
        cursor.execute('DELETE FROM checkin_records')
        # 重置自增ID
        cursor.execute('DELETE FROM sqlite_sequence WHERE name = ?', ('checkin_records',))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500