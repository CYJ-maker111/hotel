import enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


class Mode(enum.Enum):
    COOL = "cool"
    HEAT = "heat"


class FanSpeed(enum.Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def priority(self) -> int:
        # 高风>中风>低风
        return self.value


class PowerState(enum.Enum):
    OFF = "off"          # 房间空调关闭
    WAITING = "waiting"  # 有送风请求，但未被调度
    SERVING = "serving"  # 正在送风


DEFAULT_TEMP = 25.0


@dataclass
class ACRequest:
    room_id: int
    mode: Mode
    target_temp: float
    fan_speed: FanSpeed
    # 统计与调度相关
    total_served_seconds: int = 0       # 累计被送风的秒数
    waiting_seconds: int = 0            # 当前轮等待秒数（用于时间片调度）
    active: bool = True                 # 是否仍然有效（达到目标温度后会失效）


@dataclass
class Room:
    room_id: int
    initial_temp: float = DEFAULT_TEMP
    current_temp: float = DEFAULT_TEMP
    mode: Mode = Mode.COOL
    target_temp: float = DEFAULT_TEMP
    fan_speed: FanSpeed = FanSpeed.MEDIUM
    state: PowerState = PowerState.OFF

    # 计费相关
    energy_used: float = 0.0   # 累计“度”
    cost: float = 0.0          # 累计费用（元）

    # 统计相关
    total_served_seconds: int = 0
    total_waiting_seconds: int = 0

    def reset(self) -> None:
        self.current_temp = self.initial_temp
        self.state = PowerState.OFF
        self.energy_used = 0.0
        self.cost = 0.0
        self.total_served_seconds = 0
        self.total_waiting_seconds = 0


class Scheduler:
    """
    中央空调调度器：
    - 限制同时送风的房间数量 capacity
    - 实现优先级调度（高风>中风>低风，新的高优先级可抢占）
    - 实现时间片调度（相同风速，等待满 time_slice 秒后，轮转抢占服务时间最长的房间）
    """

    def __init__(self, capacity: int, time_slice: int):
        self.capacity = capacity
        self.time_slice = time_slice

        # room_id -> ACRequest
        self.active_requests: Dict[int, ACRequest] = {}
        self.waiting_requests: Dict[int, ACRequest] = {}

    def submit_request(self, request: ACRequest) -> None:
        """
        调节风速等操作会产生新的送风请求；只调温不产生新请求。
        """
        # 如果房间已有旧请求，先失效
        if request.room_id in self.active_requests:
            self.active_requests[request.room_id].active = False
            del self.active_requests[request.room_id]
        if request.room_id in self.waiting_requests:
            self.waiting_requests[request.room_id].active = False
            del self.waiting_requests[request.room_id]

        # 有空位就直接进入服务
        if len(self.active_requests) < self.capacity:
            self.active_requests[request.room_id] = request
            return

        # 检查是否可以凭优先级抢占
        lowest = self._find_lowest_priority_active()
        if lowest and request.fan_speed.priority > lowest.fan_speed.priority:
            # 抢占：把被抢占的放入等待队列，新请求进入服务
            self.waiting_requests[lowest.room_id] = lowest
            del self.active_requests[lowest.room_id]
            self.active_requests[request.room_id] = request
        else:
            # 不能抢占，进入等待队列
            self.waiting_requests[request.room_id] = request

    def remove_request(self, room_id: int) -> None:
        """
        房间达到目标温度后自动停止送风，请求失效。
        """
        if room_id in self.active_requests:
            del self.active_requests[room_id]
        if room_id in self.waiting_requests:
            del self.waiting_requests[room_id]

    def _find_lowest_priority_active(self) -> Optional[ACRequest]:
        if not self.active_requests:
            return None
        # 先按优先级，从低到高；若优先级相同，可按累计服务时间从小到大
        return sorted(
            self.active_requests.values(),
            key=lambda r: (r.fan_speed.priority, r.total_served_seconds),
        )[0]

    def tick(self, delta_seconds: int) -> None:
        """
        每经过 delta_seconds（通常为 1 秒）：
        - 更新活动请求的服务时间
        - 更新等待请求的等待时间
        - 根据时间片调度规则，可能进行轮转
        """
        if delta_seconds <= 0:
            return

        # 更新时间
        for req in self.active_requests.values():
            req.total_served_seconds += delta_seconds

        for req in self.waiting_requests.values():
            req.waiting_seconds += delta_seconds

        # 时间片调度：相同风速的等待请求，等待满 time_slice 后，
        # 抢占同风速中服务时间最长的活动请求
        if self.time_slice <= 0:
            return

        # 收集所有等待时间达到时间片的请求
        ready_to_rotate: List[ACRequest] = [
            r for r in self.waiting_requests.values() if r.waiting_seconds >= self.time_slice
        ]

        for waiting_req in ready_to_rotate:
            same_speed_actives = [
                r for r in self.active_requests.values()
                if r.fan_speed == waiting_req.fan_speed
            ]
            if not same_speed_actives:
                # 当前无同风速服务中的房间，直接顶替一个优先级不高于自己的房间
                lowest = self._find_lowest_priority_active()
                if not lowest:
                    continue
                if lowest.fan_speed.priority <= waiting_req.fan_speed.priority:
                    # 轮转
                    del self.waiting_requests[waiting_req.room_id]
                    waiting_req.waiting_seconds = 0
                    self.waiting_requests[lowest.room_id] = lowest
                    del self.active_requests[lowest.room_id]
                    self.active_requests[waiting_req.room_id] = waiting_req
                continue

            # 找到同风速中服务时间最长的房间
            victim = sorted(
                same_speed_actives,
                key=lambda r: r.total_served_seconds,
                reverse=True,
            )[0]

            # 轮转：victim 进入等待，新请求进入服务
            del self.waiting_requests[waiting_req.room_id]
            waiting_req.waiting_seconds = 0
            self.waiting_requests[victim.room_id] = victim
            del self.active_requests[victim.room_id]
            self.active_requests[waiting_req.room_id] = waiting_req


class CentralACSystem:
    """
    自助计费式中央空调系统的核心逻辑：
    - 房间管理
    - 模式 / 温度 / 风速控制
    - 调度（通过 Scheduler）
    - 计费与详单
    - 简单统计
    """

    def __init__(self, room_count: int, service_capacity: int, time_slice_seconds: int = 60):
        self.rooms: Dict[int, Room] = {
            i: Room(room_id=i) for i in range(1, room_count + 1)
        }
        self.scheduler = Scheduler(service_capacity, time_slice_seconds)
        self.current_time: int = 0  # 模拟时间（秒）

        # 计费参数
        self.price_per_energy = 1.0  # 1 元 / 度

    # --------- 客户端操作接口 ---------
    def power_on(self, room_id: int, mode: Mode, target_temp: float, fan_speed: FanSpeed) -> None:
        room = self.rooms[room_id]
        room.mode = mode
        room.target_temp = self._clamp_target_temp(mode, target_temp)
        room.fan_speed = fan_speed
        room.state = PowerState.WAITING

        req = ACRequest(
            room_id=room_id,
            mode=mode,
            target_temp=room.target_temp,
            fan_speed=fan_speed,
        )
        self.scheduler.submit_request(req)

    def power_off(self, room_id: int) -> None:
        room = self.rooms[room_id]
        room.state = PowerState.OFF
        self.scheduler.remove_request(room_id)

    def adjust_temperature(self, room_id: int, new_target_temp: float) -> None:
        """
        只调温不算新的请求，因此不触发调度器 submit_request。
        按模式限制温控范围。
        """
        room = self.rooms[room_id]
        room.target_temp = self._clamp_target_temp(room.mode, new_target_temp)

    def adjust_fan_speed(self, room_id: int, new_fan_speed: FanSpeed) -> None:
        """
        调节风速算作一次新的送风请求。
        """
        room = self.rooms[room_id]
        room.fan_speed = new_fan_speed
        room.state = PowerState.WAITING
        req = ACRequest(
            room_id=room_id,
            mode=room.mode,
            target_temp=room.target_temp,
            fan_speed=new_fan_speed,
        )
        self.scheduler.submit_request(req)

    # --------- 模拟时间推进与物理/计费模型 ---------
    def tick(self, delta_seconds: int = 1) -> None:
        """
        模拟时间前进 delta_seconds 秒，更新：
        - 调度器状态
        - 各房间温度
        - 能耗与费用
        - 自动停止 / 重启逻辑
        """
        if delta_seconds <= 0:
            return

        for _ in range(delta_seconds):
            self.current_time += 1
            self.scheduler.tick(1)
            self._update_rooms_per_second()

    def _update_rooms_per_second(self) -> None:
        # 根据调度器状态更新房间状态
        active_ids = set(self.scheduler.active_requests.keys())
        waiting_ids = set(self.scheduler.waiting_requests.keys())

        for room_id, room in self.rooms.items():
            if room.state == PowerState.OFF:
                # 关机状态：每分钟变化 0.5 度，趋向初始温度
                self._update_room_temp_off(room)
                continue

            if room_id in active_ids:
                room.state = PowerState.SERVING
                room.total_served_seconds += 1
                self._update_room_serving(room)
            elif room_id in waiting_ids:
                room.state = PowerState.WAITING
                room.total_waiting_seconds += 1
                # 等待状态，假定不送风，温度按关机逻辑回归
                self._update_room_temp_off(room)
            else:
                # 无任何请求，视作关机
                room.state = PowerState.OFF
                self._update_room_temp_off(room)

        # 自动停止和重启的逻辑放在温度更新之后处理
        self._auto_stop_and_restart()

    def _update_room_serving(self, room: Room) -> None:
        """
        送风时温度变化与能耗：
        - 中风：每分钟变化 0.5 度
        - 高风：变化率提高 20% -> 0.6 度/分钟
        - 低风：变化率降低 20% -> 0.4 度/分钟
        - 制冷：温度下降；制热：温度上升
        - 耗电标准：
            高风：1 度/1 分钟
            中风：1 度/2 分钟
            低风：1 度/3 分钟
        """
        # 温度变化率（度/分钟）
        base_rate = 0.5  # 中风
        if room.fan_speed == FanSpeed.HIGH:
            temp_rate_per_min = base_rate * 1.2
        elif room.fan_speed == FanSpeed.LOW:
            temp_rate_per_min = base_rate * 0.8
        else:
            temp_rate_per_min = base_rate

        temp_rate_per_sec = temp_rate_per_min / 60.0

        # 根据模式决定增减方向
        if room.mode == Mode.COOL:
            # 制冷：房间温度向下接近目标温度
            if room.current_temp > room.target_temp:
                room.current_temp -= temp_rate_per_sec
                if room.current_temp < room.target_temp:
                    room.current_temp = room.target_temp
        else:
            # 制热：房间温度向上接近目标温度
            if room.current_temp < room.target_temp:
                room.current_temp += temp_rate_per_sec
                if room.current_temp > room.target_temp:
                    room.current_temp = room.target_temp

        # 能耗（度/分钟）
        if room.fan_speed == FanSpeed.HIGH:
            energy_rate_per_min = 1.0
        elif room.fan_speed == FanSpeed.MEDIUM:
            energy_rate_per_min = 0.5
        else:  # LOW
            energy_rate_per_min = 1.0 / 3.0

        energy_rate_per_sec = energy_rate_per_min / 60.0
        room.energy_used += energy_rate_per_sec
        room.cost = room.energy_used * self.price_per_energy

    def _update_room_temp_off(self, room: Room) -> None:
        """
        关机 / 未送风状态下：
        - 每分钟变化 0.5 度，直到回到初始温度
        """
        rate_per_sec = 0.5 / 60.0
        if abs(room.current_temp - room.initial_temp) < rate_per_sec:
            room.current_temp = room.initial_temp
            return

        if room.current_temp < room.initial_temp:
            room.current_temp += rate_per_sec
        elif room.current_temp > room.initial_temp:
            room.current_temp -= rate_per_sec

    def _auto_stop_and_restart(self) -> None:
        """
        - 房间温度达到目标值后，客户端自动发送停止送风请求
        - 之后，当房间温度超过目标温度 1 度时，自动重新发起送风请求
        """
        for room_id, room in self.rooms.items():
            # 已在服务中的房间是否达到目标温度
            if room.state == PowerState.SERVING:
                if room.mode == Mode.COOL and room.current_temp <= room.target_temp:
                    # 停止送风
                    self.power_off(room_id)
                elif room.mode == Mode.HEAT and room.current_temp >= room.target_temp:
                    self.power_off(room_id)
                continue

            # 非服务状态下，是否需要重新开启
            if room.state in (PowerState.OFF, PowerState.WAITING):
                if room.mode == Mode.COOL:
                    # 温度重新升高超过目标温度 1 度以上时重启
                    if room.current_temp >= room.target_temp + 1.0:
                        # 重新发起送风请求，风速沿用现有设置
                        self.power_on(room_id, room.mode, room.target_temp, room.fan_speed)
                else:
                    # 制热模式下，温度降低超过 1 度时重启
                    if room.current_temp <= room.target_temp - 1.0:
                        self.power_on(room_id, room.mode, room.target_temp, room.fan_speed)

    def _clamp_target_temp(self, mode: Mode, temp: float) -> float:
        if mode == Mode.COOL:
            return max(18.0, min(25.0, temp))
        else:
            return max(25.0, min(30.0, temp))

    # --------- 监控与报表 ---------
    def get_room_status(self, room_id: int) -> Dict:
        room = self.rooms[room_id]
        return {
            "room_id": room.room_id,
            "mode": room.mode.value,
            "target_temp": room.target_temp,
            "current_temp": round(room.current_temp, 2),
            "fan_speed": room.fan_speed.name,
            "state": room.state.value,
            "energy_used": round(room.energy_used, 4),
            "cost": round(room.cost, 2),
            "served_seconds": room.total_served_seconds,
            "waiting_seconds": room.total_waiting_seconds,
        }

    def get_all_rooms_status(self) -> List[Dict]:
        return [self.get_room_status(rid) for rid in sorted(self.rooms.keys())]

    def get_bill_for_room(self, room_id: int) -> Dict:
        room = self.rooms[room_id]
        return {
            "room_id": room.room_id,
            "total_energy": round(room.energy_used, 4),
            "total_cost": round(room.cost, 2),
            "total_served_minutes": round(room.total_served_seconds / 60.0, 2),
        }

    def get_summary_report(self) -> Dict:
        """
        简单统计报表：可以扩展为按时间范围查询。
        """
        total_energy = sum(r.energy_used for r in self.rooms.values())
        total_cost = sum(r.cost for r in self.rooms.values())
        total_served_seconds = sum(r.total_served_seconds for r in self.rooms.values())
        return {
            "time_seconds": self.current_time,
            "total_energy": round(total_energy, 4),
            "total_cost": round(total_cost, 2),
            "total_served_minutes": round(total_served_seconds / 60.0, 2),
        }


class CommandDebouncer:
    """
    温度调节按钮防抖：
    - 连续两次或多次指令时间间隔 < 1 秒，只保留最后一次参数
    - 时间间隔 >= 1 秒，则两次请求都发送

    使用方式：传入一系列 (timestamp, value)（时间单位秒，可为 float），
    返回需要真正发送的指令序列。
    """

    @staticmethod
    def debounce(commands: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if not commands:
            return []
        commands = sorted(commands, key=lambda c: c[0])
        result: List[Tuple[float, float]] = []

        group_last_cmd = commands[0]

        for ts, val in commands[1:]:
            # 与上一条的间隔
            if ts - group_last_cmd[0] < 1.0:
                # 仍处于同一组快速操作，用最新指令覆盖
                group_last_cmd = (ts, val)
            else:
                # 前一组结束，发送最后一条
                result.append(group_last_cmd)
                group_last_cmd = (ts, val)

        # 最后一组
        result.append(group_last_cmd)
        return result


def demo():
    """
    一个简单的演示：
    - 酒店有 5 间房，中央空调同时最多服务 2 间房，时间片 30 秒
    - 房间 1、2、3 发起不同风速的制冷请求
    """
    system = CentralACSystem(room_count=5, service_capacity=2, time_slice_seconds=30)

    # 房间 1：高风制冷到 22 度
    system.power_on(room_id=1, mode=Mode.COOL, target_temp=22.0, fan_speed=FanSpeed.HIGH)
    # 房间 2：中风制冷到 23 度
    system.power_on(room_id=2, mode=Mode.COOL, target_temp=23.0, fan_speed=FanSpeed.MEDIUM)
    # 房间 3：低风制冷到 24 度（将排队等待）
    system.power_on(room_id=3, mode=Mode.COOL, target_temp=24.0, fan_speed=FanSpeed.LOW)

    # 模拟 20 分钟（1200 秒）
    system.tick(1200)

    print("=== 房间状态 ===")
    for status in system.get_all_rooms_status():
        print(status)

    print("\n=== 账单示例（房间 1）===")
    print(system.get_bill_for_room(1))

    print("\n=== 总体统计报表 ===")
    print(system.get_summary_report())


if __name__ == "__main__":
    demo()


