from typing import Tuple

from .models import RoomRepository, Mode, FanSpeed, PowerState, Room


class Server:
    """
    服务对象：只负责温控参数设置与温度变化，不做调度与计费。
    """

    def __init__(self, rooms: RoomRepository):
        self.rooms = rooms

    def set_target(self, room_id: int, current_room_temp: float) -> Tuple[str, float, float]:
        """
        设置初次开机的模式与目标温度，返回 (mode, target_temp, fee_rate)。
        为简化：默认使用制冷模式，目标温度 25 度，可根据需要扩展为前端传入。
        """
        room = self.rooms.get(room_id)
        room.current_temp = current_room_temp
        room.mode = Mode.COOL
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

    def update_temperature(self, room_id: int, delta_seconds: int) -> float:
        """
        根据房间当前模式、目标温度和风速更新温度，并返回本段时间的能耗（度）。
        温控与能耗模型直接复用原先 central_ac 中的逻辑。
        """
        room = self.rooms.get(room_id)
        if room.state != PowerState.SERVING:
            return 0.0

        # 温度变化率（度/分钟）
        base_rate = 0.5  # 中风
        if room.fan_speed == FanSpeed.HIGH:
            temp_rate_per_min = base_rate * 1.2
        elif room.fan_speed == FanSpeed.LOW:
            temp_rate_per_min = base_rate * 0.8
        else:
            temp_rate_per_min = base_rate

        temp_rate_per_sec = temp_rate_per_min / 60.0

        for _ in range(delta_seconds):
            if room.mode == Mode.COOL:
                if room.current_temp > room.target_temp:
                    room.current_temp -= temp_rate_per_sec
                    if room.current_temp < room.target_temp:
                        room.current_temp = room.target_temp
            else:
                if room.current_temp < room.target_temp:
                    room.current_temp += temp_rate_per_sec
                    if room.current_temp > room.target_temp:
                        room.current_temp = room.target_temp

        # 能耗（度/分钟）
        if room.fan_speed == FanSpeed.HIGH:
            energy_rate_per_min = 1.0
        elif room.fan_speed == FanSpeed.MEDIUM:
            energy_rate_per_min = 0.5
        else:
            energy_rate_per_min = 1.0 / 3.0

        energy_rate_per_sec = energy_rate_per_min / 60.0
        energy_used = energy_rate_per_sec * delta_seconds
        room.energy_used += energy_used
        return energy_used

    @staticmethod
    def _calc_fee_rate(fan_speed: FanSpeed) -> float:
        if fan_speed == FanSpeed.HIGH:
            return 1.0
        if fan_speed == FanSpeed.MEDIUM:
            return 0.5
        return 1.0 / 3.0


