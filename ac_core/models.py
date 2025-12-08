import enum
from dataclasses import dataclass
from typing import Dict


class Mode(enum.Enum):
    COOL = "cool"
    HEAT = "heat"


class FanSpeed(enum.Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def priority(self) -> int:
        # 高风 > 中风 > 低风
        return self.value


class PowerState(enum.Enum):
    OFF = "off"          # 关机
    WAITING = "waiting"  # 等待队列中
    SERVING = "serving"  # 正在送风
    PAUSED = "paused"    # 暂停服务（回温状态）


DEFAULT_TEMP = 25.0


@dataclass
class Room:
    room_id: int
    initial_temp: float = DEFAULT_TEMP
    current_temp: float = DEFAULT_TEMP
    mode: Mode = Mode.COOL
    target_temp: float = DEFAULT_TEMP
    fan_speed: FanSpeed = FanSpeed.MEDIUM
    state: PowerState = PowerState.OFF

    # 计费相关（累计）
    cost: float = 0.0

    # 统计相关
    total_served_seconds: int = 0
    total_waiting_seconds: int = 0


class RoomRepository:
    """
    简单的房间存储（内存版），可替换为数据库。
    """

    def __init__(self, room_count: int):
        # 不设置固定的初始温度，使用默认温度
        # 测试用例的初始温度将通过/api/rooms/initialize接口设置
        self.rooms: Dict[int, Room] = {}
        for i in range(1, room_count + 1):
            self.rooms[i] = Room(
                room_id=i,
                initial_temp=DEFAULT_TEMP,
                current_temp=DEFAULT_TEMP  # 初始时使用默认温度
            )

    def get(self, room_id: int) -> Room:
        return self.rooms[room_id]

    def all(self):
        return list(self.rooms.values())


