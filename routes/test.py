from flask import Blueprint, jsonify, request
import re
import os
from threading import Lock

# 创建测试用例蓝图
test_bp = Blueprint('test', __name__)

# 测试用例状态
class TestState:
    def __init__(self):
        self.test_cases = []  # 存储解析后的测试用例
        self.current_step = 0  # 当前执行的步骤
        self.initial_temperatures = {}  # 存储房间初始温度
        self.default_wind_speed = "MEDIUM"  # 默认风速
        self.lock = Lock()

test_state = TestState()

# 全局变量存储解析后的测试用例（保持向后兼容）
test_cases = test_state.test_cases
current_minute = test_state.current_step
test_lock = test_state.lock

# 测试用例文件路径配置
TEST_FILES = {
    'cooling': r'c:\\Users\\LJM\\Desktop\\ac_system\\hotel\\制冷.txt',
    'heating': r'c:\\Users\\LJM\\Desktop\\ac_system\\hotel\\制热.txt',
    'default': r'./test.txt'
}

@test_bp.route('/api/test/load', methods=['GET'])
def load_test_cases():
    """加载并解析测试用例文件"""
    global test_cases, current_minute
    
    try:
        # 获取测试类型参数
        test_type = request.args.get('type', 'default')
        
        # 根据测试类型选择对应的文件路径
        if test_type in TEST_FILES:
            file_path = TEST_FILES[test_type]
            test_name = '制冷' if test_type == 'cooling' else '制热' if test_type == 'heating' else '默认'
        else:
            file_path = TEST_FILES['default']
            test_name = '默认'
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'message': f'{test_name}测试用例文件不存在: {file_path}'
            })
        
        # 解析测试用例文件
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        test_cases = []
        
        # 遍历每一行，解析时刻和操作
        for line in content:
            line = line.strip()
            if not line or line.startswith('制冷测试用例'):
                continue
            
            # 解析初始温度设置
            if "初始温度" in line:
                # 匹配房间初始温度，例如：R1初始温度32，R2初始温度28
                temp_matches = re.findall(r'R(\d+)初始温度(\d+)', line)
                for room_num, temp in temp_matches:
                    test_state.initial_temperatures[f'R{room_num}'] = int(temp)
                
                # 解析默认风速
                wind_match = re.search(r'风速默认为([A-Z]+)', line)
                if wind_match:
                    test_state.default_wind_speed = wind_match.group(1)
                continue
            
            # 匹配时刻和操作，支持中英文冒号
            match = re.match(r'时刻(\d+)[：:](.*)', line)
            if match:
                minute = int(match.group(1))
                operations_str = match.group(2).strip()
                
                # 解析操作
                operations = []
                if operations_str != '无操作':
                    # 分割多个操作（以逗号分隔）
                    for op in operations_str.split('，'):
                        op = op.strip()
                        
                        # 解析开机操作
                        if op.endswith('开机'):
                            room_id = op[:2]  # 提取R1-R5
                            operations.append({
                                'type': 'power_on',
                                'room_id': room_id
                            })
                        # 解析关机操作
                        elif op.endswith('关机'):
                            room_id = op[:2]  # 提取R1-R5
                            operations.append({
                                'type': 'power_off',
                                'room_id': room_id
                            })
                        # 解析调温操作
                        elif '调温' in op:
                            room_id = op[:2]  # 提取R1-R5
                            temp_match = re.search(r'调温(\d+)℃?', op)
                            if temp_match:
                                temp = int(temp_match.group(1))
                                operations.append({
                                    'type': 'adjust_temperature',
                                    'room_id': room_id,
                                    'target_temp': temp
                                })
                        # 解析调风速操作
                        elif '调风速' in op:
                            room_id = op[:2]  # 提取R1-R5
                            speed_match = re.search(r'调风速为?(HIGH|MEDIUM|LOW|高|中|低)', op)
                            if speed_match:
                                speed = speed_match.group(1)
                                # 转换中文风速为英文
                                speed_map = {'高': 'HIGH', '中': 'MEDIUM', '低': 'LOW'}
                                if speed in speed_map:
                                    speed = speed_map[speed]
                                operations.append({
                                    'type': 'adjust_wind_speed',
                                    'room_id': room_id,
                                    'speed': speed
                                })
                
                test_cases.append({
                    'minute': minute,
                    'operations': operations
                })
        
        # 按时刻排序
        test_cases.sort(key=lambda x: x['minute'])
        
        # 重置当前时刻
        current_minute = 0
        test_state.current_step = 0  # 同步重置test_state
        
        return jsonify({
            'success': True,
            'message': f'成功加载{test_name}测试用例，共{len(test_cases)}个时刻',
            'total_minutes': len(test_cases),
            'test_cases': test_cases,
            'initial_temperatures': test_state.initial_temperatures,
            'default_wind_speed': test_state.default_wind_speed
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'加载测试用例失败: {str(e)}'
        })

@test_bp.route('/api/test/start', methods=['POST'])
def start_test():
    """开始执行当前时刻的测试用例操作"""
    global current_minute, test_cases
    
    with test_lock:
        # 检查是否有测试用例
        if not test_cases:
            return jsonify({
                'success': False,
                'message': '请先加载测试用例'
            })
        
        # 检查当前时刻是否有效
        if current_minute >= len(test_cases):
            return jsonify({
                'success': False,
                'message': '所有测试用例已执行完毕'
            })
        
        # 获取当前时刻的测试用例
        current_case = test_cases[current_minute]
        
        # 这里返回测试用例信息，实际执行将在前端进行
        return jsonify({
            'success': True,
            'message': f'开始执行时刻{current_minute}的操作',
            'current_minute': current_minute,
            'total_minutes': len(test_cases),
            'operations': current_case['operations'],
            'initial_temperatures': test_state.initial_temperatures,
            'default_wind_speed': test_state.default_wind_speed
        })

@test_bp.route('/api/test/next', methods=['POST'])
def next_minute():
    """前进到下一个时刻"""
    global current_minute, test_cases
    
    with test_lock:
        # 检查是否有测试用例
        if not test_cases:
            return jsonify({
                'success': False,
                'message': '请先加载测试用例'
            })
        
        # 前进到下一个时刻
        current_minute += 1
        test_state.current_step = current_minute  # 同步更新test_state
        
        # 检查是否还有下一个时刻
        if current_minute >= len(test_cases):
            return jsonify({
                'success': True,
                'message': '所有测试用例已执行完毕',
                'current_minute': current_minute,
                'total_minutes': len(test_cases),
                'has_next': False
            })
        
        # 返回下一个时刻的信息（但不执行操作，由前端调用start来执行）
        return jsonify({
            'success': True,
            'message': f'已前进到时刻{current_minute}',
            'current_minute': current_minute,
            'total_minutes': len(test_cases),
            'has_next': True
        })

@test_bp.route('/api/test/status', methods=['GET'])
def get_test_status():
    """获取测试状态"""
    return jsonify({
        'has_test_cases': len(test_cases) > 0,
        'current_minute': current_minute,
        'total_minutes': len(test_cases),
        'test_cases': test_cases,
        'initial_temperatures': test_state.initial_temperatures,
        'default_wind_speed': test_state.default_wind_speed
    })
