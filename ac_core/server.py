from typing import Tuple
from decimal import Decimal, ROUND_HALF_UP

from .models import RoomRepository, Mode, FanSpeed, PowerState, Room


class Server:
    """
    服务对象：只负责温控参数设置与温度变化，不做调度与计费。
    """

    def __init__(self, rooms: RoomRepository):
        self.rooms = rooms

    def set_target(self, room_id: int, current_room_temp: float, mode: Mode = Mode.COOL) -> Tuple[str, float, float]:
        """
        设置初次开机的模式与目标温度，返回 (mode, target_temp, fee_rate)。
        支持前端传入模式，默认为制冷模式。
        默认目标温度统一设置为25℃，其他调温操作通过update_target_temperature或测试用例进行。
        """
        room = self.rooms.get(room_id)
        room.current_temp = self._normalize_temp(current_room_temp)
        room.mode = mode
        
        # 默认目标温度统一设置为25℃，确保温度值为整数
        room.target_temp = 25.0
            
        room.fan_speed = FanSpeed.MEDIUM
        room.state = PowerState.SERVING
        fee_rate = self._calc_fee_rate(room.fan_speed)
        return room.mode.value, room.target_temp, fee_rate

    def update_speed(self, room_id: int, new_speed: FanSpeed) -> float:
        """
        更新风速，返回新的费用费率。
        """
        room = self.rooms.get(room_id)
        room.fan_speed = new_speed
        return self._calc_fee_rate(new_speed)
    
    def update_target_temperature(self, room_id: int, new_target_temp: float) -> float:
        """
        更新目标温度，返回新的目标温度。
        规范化目标温度，确保精度一致。
        """
        room = self.rooms.get(room_id)
        # 规范化目标温度，保留2位小数（温度通常只需要1-2位小数精度）
        room.target_temp = self._normalize_temp(new_target_temp)
        return room.target_temp

    def update_temperature(self, room_id: int, delta_seconds: int) -> float:
        """
        根据房间当前模式、目标温度和风速更新温度，并返回本段时间的费用（元）。
        温控与费用模型直接复用原先 central_ac 中的逻辑。
        
        回温算法严格按照以下三种情况执行：
        1. 当房间关机时回温，每分钟0.5摄氏度。
        2. 当房间达到目标温度后回温，每分钟0.5摄氏度，当回温达到1摄氏度时，发送送风请求。
        3. 制冷模式下当前温度低于目标温度或制热模式下当前温度高于目标温度时，通过回温恢复到目标温度。
        """
        room = self.rooms.get(room_id)
        cost = 0.0
        temp_change = 0.0
        # 每次计算前先规范化当前温度，减少累计误差
        room.current_temp = self._normalize_temp(room.current_temp)
        
        if room.state == PowerState.SERVING:
            # 温度变化率（度/分钟）
            if room.fan_speed == FanSpeed.HIGH:
                temp_rate_per_min = 1.0  # 高风：1℃/1分钟
            elif room.fan_speed == FanSpeed.MEDIUM:
                temp_rate_per_min = 0.5  # 中风：1℃/2分钟
            else:
                temp_rate_per_min = 1.0 / 3.0  # 低风：1℃/3分钟

            temp_rate_per_sec = temp_rate_per_min / 60.0

            # 温度对齐容差：如果温度与目标温度差值小于此值，立即对齐
            temp_tolerance = 0.005
            
            for _ in range(delta_seconds):
                if room.mode == Mode.COOL:
                    # 先检查是否已经达到或接近目标温度
                    temp_diff = room.current_temp - room.target_temp
                    if abs(temp_diff) <= temp_tolerance:
                        # 立即对齐到目标温度
                        room.current_temp = self._normalize_temp(room.target_temp)
                        # 达到目标温度，更新房间状态为暂停服务（回温）状态
                        room.state = PowerState.PAUSED
                        # 通知调度器房间状态变化，需要从服务队列移除
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                        break
                    
                    if room.current_temp > room.target_temp:
                        # 如果当前温度大于目标温度，继续降温
                        room.current_temp -= temp_rate_per_sec
                        room.current_temp = self._normalize_temp(room.current_temp)
                        temp_change += temp_rate_per_sec
                        
                        # 每次变化后立即检查是否达到目标温度
                        temp_diff = room.current_temp - room.target_temp
                        if abs(temp_diff) <= temp_tolerance or room.current_temp <= room.target_temp:
                            room.current_temp = self._normalize_temp(room.target_temp)
                            # 达到目标温度，更新房间状态为暂停服务（回温）状态
                            room.state = PowerState.PAUSED
                            # 通知调度器房间状态变化，需要从服务队列移除
                            if hasattr(self, 'scheduler') and self.scheduler is not None:
                                self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                            break
                    else:
                        # 情况3：制冷模式下当前温度低于目标温度
                        # 直接进入PAUSED状态，利用回温算法让温度自然上升，不计费
                        old_state = room.state
                        room.state = PowerState.PAUSED
                        # 通知调度器房间状态变化，需要从服务队列移除
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                        
                        # 处理情况3：回温至目标温度
                        temp_rate_per_min = 0.5  # 回温速率：0.5℃/分钟
                        temp_rate_per_sec = temp_rate_per_min / 60.0
                        
                        for _ in range(delta_seconds):
                            room.current_temp += temp_rate_per_sec
                            room.current_temp = self._normalize_temp(room.current_temp)
                            
                            # 每次变化后立即检查是否达到目标温度
                            temp_diff = room.current_temp - room.target_temp
                            if abs(temp_diff) <= temp_tolerance or room.current_temp >= room.target_temp:
                                room.current_temp = self._normalize_temp(room.target_temp)
                                break
                        return 0.0  # 回温过程不计费
                else:  # HEAT模式
                    # 先检查是否已经达到或接近目标温度
                    temp_diff = room.target_temp - room.current_temp
                    if abs(temp_diff) <= temp_tolerance:
                        # 立即对齐到目标温度
                        room.current_temp = self._normalize_temp(room.target_temp)
                        # 达到目标温度，更新房间状态为暂停服务（回温）状态
                        room.state = PowerState.PAUSED
                        # 通知调度器房间状态变化，需要从服务队列移除
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                        break
                    
                    if room.current_temp < room.target_temp:
                        # 如果当前温度小于目标温度，继续升温
                        room.current_temp += temp_rate_per_sec
                        room.current_temp = self._normalize_temp(room.current_temp)
                        temp_change += temp_rate_per_sec
                        
                        # 每次变化后立即检查是否达到目标温度
                        temp_diff = room.target_temp - room.current_temp
                        if abs(temp_diff) <= temp_tolerance or room.current_temp >= room.target_temp:
                            room.current_temp = self._normalize_temp(room.target_temp)
                            # 达到目标温度，更新房间状态为暂停服务（回温）状态
                            room.state = PowerState.PAUSED
                            # 通知调度器房间状态变化，需要从服务队列移除
                            if hasattr(self, 'scheduler') and self.scheduler is not None:
                                self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                            break
                    else:
                        # 情况3：制热模式下当前温度高于目标温度
                        # 直接进入PAUSED状态，利用回温算法让温度自然下降，不计费
                        old_state = room.state
                        room.state = PowerState.PAUSED
                        # 通知调度器房间状态变化，需要从服务队列移除
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            self.scheduler._on_room_state_changed(room_id, PowerState.PAUSED)
                        
                        # 处理情况3：回温至目标温度
                        temp_rate_per_min = 0.5  # 回温速率：0.5℃/分钟
                        temp_rate_per_sec = temp_rate_per_min / 60.0
                        
                        for _ in range(delta_seconds):
                            room.current_temp -= temp_rate_per_sec
                            room.current_temp = self._normalize_temp(room.current_temp)
                            
                            # 每次变化后立即检查是否达到目标温度
                            temp_diff = room.target_temp - room.current_temp
                            if abs(temp_diff) <= temp_tolerance or room.current_temp <= room.target_temp:
                                room.current_temp = self._normalize_temp(room.target_temp)
                                break
                        return 0.0  # 回温过程不计费
              
            # 费用（元）= 温度变化量（℃）* 1元/1℃
            cost = self._normalize_temp(temp_change, 3)  # 计费费率：1元/1℃，所以费用=温度变化量
            
        elif room.state == PowerState.PAUSED:
            # 情况2：房间达到目标温度后的回温算法：每分钟回温0.5℃
            # 当房间达到目标温度后，应保持PAUSED状态，只有当温度变化超过阈值时才转为WAITING
            # 不要因为房间不在服务队列中就直接转为WAITING状态
            
            temp_rate_per_min = 0.5  # 每分钟回温0.5℃
            temp_rate_per_sec = temp_rate_per_min / 60.0
            
            # 温度对齐容差
            temp_tolerance = 0.005
            
            for _ in range(delta_seconds):
                if room.mode == Mode.COOL:
                    # 制冷模式下，暂停后温度上升
                    room.current_temp += temp_rate_per_sec
                    room.current_temp = self._normalize_temp(room.current_temp)
                    # 不需要计算temp_change，因为回温不计费
                    
                    # 当室温回温达到1℃时重新发送送风请求
                    threshold_temp = room.target_temp + 1.0
                    # 使用容差值解决浮点数精度问题
                    threshold_tolerance = 0.001
                    # 当达到阈值时，转换为WAITING状态
                    if room.current_temp >= threshold_temp - threshold_tolerance:
                        room.state = PowerState.WAITING  # 进入等待队列，而不是直接SERVING
                        # 确保重新添加到等待队列，由调度器决定何时进入服务队列
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            # 从服务队列移除（如果存在）
                            if room_id in self.scheduler.served_queue.all_rooms():
                                self.scheduler.served_queue.pop(room_id)
                            # 添加到等待队列（如果不存在）
                            if room_id not in self.scheduler.waiting_queue.all_rooms():
                                self.scheduler.waiting_queue.push(room_id)
                                # 重置等待计时器
                                self.scheduler.wait_timer.reset_timer(room_id)
                        return 0.0  # 回温不计费
                else:  # HEAT模式
                    # 制热模式下，暂停后温度下降
                    room.current_temp -= temp_rate_per_sec
                    room.current_temp = self._normalize_temp(room.current_temp)
                    # 不需要计算temp_change，因为回温不计费
                    
                    # 当室温回温达到1℃时重新发送送风请求
                    threshold_temp = room.target_temp - 1.0
                    threshold_tolerance = 0.001
                    # 当达到阈值时，转换为WAITING状态
                    if room.current_temp <= threshold_temp + threshold_tolerance:
                        room.state = PowerState.WAITING  # 进入等待队列，而不是直接SERVING
                        # 确保重新添加到等待队列，由调度器决定何时进入服务队列
                        if hasattr(self, 'scheduler') and self.scheduler is not None:
                            # 从服务队列移除（如果存在）
                            if room_id in self.scheduler.served_queue.all_rooms():
                                self.scheduler.served_queue.pop(room_id)
                            # 添加到等待队列（如果不存在）
                            if room_id not in self.scheduler.waiting_queue.all_rooms():
                                self.scheduler.waiting_queue.push(room_id)
                                # 重置等待计时器
                                self.scheduler.wait_timer.reset_timer(room_id)
                        return 0.0  # 回温不计费
            
            # 确保回温状态不计费
            return 0.0
        
        elif room.state == PowerState.WAITING:
            # 等待状态不执行回温，温度保持不变
            return 0.0  # 不计费
            
        elif room.state == PowerState.OFF:
            # 情况1：关机时的回温：每分钟回温0.5℃，直到达到初始温度
            temp_rate_per_min = 0.5  # 每分钟回温0.5℃
            temp_rate_per_sec = temp_rate_per_min / 60.0
            
            # 温度对齐容差
            temp_tolerance = 0.005
            
            for _ in range(delta_seconds):
                temp_diff = room.current_temp - room.initial_temp
                
                # 如果已经达到或接近初始温度，立即对齐并停止
                if abs(temp_diff) <= temp_tolerance:
                    room.current_temp = self._normalize_temp(room.initial_temp)
                    break
                
                if room.current_temp < room.initial_temp:
                    room.current_temp += temp_rate_per_sec
                    room.current_temp = self._normalize_temp(room.current_temp)
                    # 每次变化后立即检查是否达到初始温度
                    temp_diff = room.current_temp - room.initial_temp
                    if abs(temp_diff) <= temp_tolerance or room.current_temp >= room.initial_temp:
                        room.current_temp = self._normalize_temp(room.initial_temp)
                        break
                elif room.current_temp > room.initial_temp:
                    room.current_temp -= temp_rate_per_sec
                    room.current_temp = self._normalize_temp(room.current_temp)
                    # 每次变化后立即检查是否达到初始温度
                    temp_diff = room.current_temp - room.initial_temp
                    if abs(temp_diff) <= temp_tolerance or room.current_temp <= room.initial_temp:
                        room.current_temp = self._normalize_temp(room.initial_temp)
                        break
            
            # 关机时回温不计费
            return 0.0
        
        # 收尾对齐：避免累计误差导致 25.01 这类偏差
        tolerance = 0.005
        if room.state in [PowerState.SERVING, PowerState.PAUSED]:
            if abs(room.current_temp - room.target_temp) < tolerance:
                room.current_temp = self._normalize_temp(room.target_temp)
        elif room.state == PowerState.OFF:
            if abs(room.current_temp - room.initial_temp) < tolerance:
                room.current_temp = self._normalize_temp(room.initial_temp)
        
        # 对于其他未知状态，不执行回温
        return cost

    @staticmethod
    def _calc_fee_rate(fan_speed: FanSpeed) -> float:
        return 1.0  # 统一计费费率：1元/1℃

    @staticmethod
    def _normalize_temp(value: float, ndigits: int = 3) -> float:
        """
        使用 Decimal 做四舍五入，将温度限定到指定小数位，减少浮点累积误差。
        默认保留 3 位小数，兼顾计算精度与显示需求。
        """
        quant = Decimal("1").scaleb(-ndigits)
        return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


