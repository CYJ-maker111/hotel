from typing import Tuple

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
        """
        room = self.rooms.get(room_id)
        room.current_temp = current_room_temp
        room.mode = mode
        
        # 根据不同模式设置不同的缺省温度
        if mode == Mode.COOL:
            # 制冷模式：缺省温度25℃
            room.target_temp = 25.0
        elif mode == Mode.HEAT:
            # 制热模式：缺省温度23℃
            room.target_temp = 23.0
        else:
            # 默认缺省温度25℃
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
        """
        room = self.rooms.get(room_id)
        room.target_temp = new_target_temp
        return new_target_temp

    def update_temperature(self, room_id: int, delta_seconds: int) -> float:
        """
        根据房间当前模式、目标温度和风速更新温度，并返回本段时间的费用（元）。
        温控与费用模型直接复用原先 central_ac 中的逻辑。
        """
        room = self.rooms.get(room_id)
        cost = 0.0
        temp_change = 0.0
        
        if room.state == PowerState.SERVING:
            # 温度变化率（度/分钟）
            if room.fan_speed == FanSpeed.HIGH:
                temp_rate_per_min = 1.0  # 高风：1℃/1分钟
            elif room.fan_speed == FanSpeed.MEDIUM:
                temp_rate_per_min = 0.5  # 中风：1℃/2分钟
            else:
                temp_rate_per_min = 1.0 / 3.0  # 低风：1℃/3分钟

            temp_rate_per_sec = temp_rate_per_min / 60.0

            for _ in range(delta_seconds):
                if room.mode == Mode.COOL:
                    if room.current_temp > room.target_temp:
                        room.current_temp -= temp_rate_per_sec
                        temp_change += temp_rate_per_sec
                        if room.current_temp <= room.target_temp:
                            room.current_temp = room.target_temp
                            # 达到目标温度，进入暂停服务（回温）状态
                            room.state = PowerState.PAUSED
                            break
                else:
                    if room.current_temp < room.target_temp:
                        room.current_temp += temp_rate_per_sec
                        temp_change += temp_rate_per_sec
                        if room.current_temp >= room.target_temp:
                            room.current_temp = room.target_temp
                            # 达到目标温度，进入暂停服务（回温）状态
                            room.state = PowerState.PAUSED
                            break
             


            # 费用（元）= 温度变化量（℃）* 1元/1℃
            cost = temp_change  # 计费费率：1元/1℃，所以费用=温度变化量
            
        elif room.state == PowerState.PAUSED:
            # 暂停服务时的回温算法：每分钟回温0.5℃
            temp_rate_per_min = 0.5  # 每分钟回温0.5℃
            temp_rate_per_sec = temp_rate_per_min / 60.0
            
            for _ in range(delta_seconds):
                if room.mode == Mode.COOL:
                    # 制冷模式下，暂停后温度上升
                    room.current_temp += temp_rate_per_sec
                    temp_change += temp_rate_per_sec
                    # 当室温回温1℃时重新发送温控请求
                    if room.current_temp >= room.target_temp + 1.0:
                        room.state = PowerState.SERVING
                        break
                else:
                    # 制热模式下，暂停后温度下降
                    room.current_temp -= temp_rate_per_sec
                    temp_change += temp_rate_per_sec
                    # 当室温回温1℃时重新发送温控请求
                    if room.current_temp <= room.target_temp - 1.0:
                        room.state = PowerState.SERVING
                        break
            

            
        elif room.state == PowerState.OFF:
            # 关机时的回温：每分钟回温0.5℃，直到达到初始温度
            temp_rate_per_min = 0.5  # 每分钟回温0.5℃
            temp_rate_per_sec = temp_rate_per_min / 60.0
            
            for _ in range(delta_seconds):
                if room.current_temp < room.initial_temp:
                    room.current_temp += temp_rate_per_sec
                    temp_change += temp_rate_per_sec
                    if room.current_temp >= room.initial_temp:
                        room.current_temp = room.initial_temp
                        break
                elif room.current_temp > room.initial_temp:
                    room.current_temp -= temp_rate_per_sec
                    temp_change += temp_rate_per_sec
                    if room.current_temp <= room.initial_temp:
                        room.current_temp = room.initial_temp
                        break
                else:
                    # 已经达到初始温度，停止回温
                    break
            


        return cost

    @staticmethod
    def _calc_fee_rate(fan_speed: FanSpeed) -> float:
        return 1.0  # 统一计费费率：1元/1℃


