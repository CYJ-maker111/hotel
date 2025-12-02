from datetime import datetime
from typing import Dict, Optional, List, Tuple

from .models import RoomRepository, Mode, FanSpeed, PowerState
from .queues import ServedQueue, WaitingQueue
from .timers import ServiceTimer, WaitTimer
from .server import Server
from .records import DetailRecord


class Scheduler:
    """
    调度对象：作为流程入口，承接用户操作并协调队列、服务对象、计时器和详单的交互。
    """

    def __init__(
        self,
        rooms: RoomRepository,
        capacity: int,
        time_slice_seconds: int,
        detail_record: DetailRecord,
    ):
        self.rooms = rooms
        self.served_queue = ServedQueue(capacity)
        self.waiting_queue = WaitingQueue()
        self.service_timer = ServiceTimer()
        self.wait_timer = WaitTimer()
        self.server = Server(rooms)
        self.detail_record = detail_record
        self.time_slice = time_slice_seconds
        # 记录当前正在服务的详单记录 id：room_id -> detail_record_id
        self.current_record_ids: Dict[int, int] = {}

    # ---------- 请求入口 ----------
    def power_on(self, room_id: int, current_room_temp: float) -> Dict:
        """
        PowerOn(RoomId, CurrentRoomTemp)
        """
        state = self.served_queue.check()
        if state.has_slot:
            # 进入服务队列
            self.served_queue.push(room_id)
            mode, target_temp, fee_rate = self.server.set_target(room_id, current_room_temp)
            self.service_timer.reset_timer(room_id)
            record_id = self.detail_record.create_record(
                room_id=room_id,
                start_time=self._now_str(),
                mode=mode,
                target_temp=target_temp,
                fan_speed=self.rooms.get(room_id).fan_speed.name,
                fee_rate=fee_rate,
                operation_type="POWER_ON",
            )
            self.current_record_ids[room_id] = record_id
            return {
                "room_id": room_id,
                "state": "serving",
                "mode": mode,
                "target_temp": target_temp,
                "current_fee": 0.0,
                "total_fee": self.detail_record.get_room_total(room_id)["total_cost"],
            }
        # 无空位，进入等待队列
        self.waiting_queue.push(room_id)
        self.wait_timer.create_timer(room_id)
        room = self.rooms.get(room_id)
        room.state = PowerState.WAITING
        return {
            "room_id": room_id,
            "state": "waiting",
        }

    def adjust_wind_speed(self, room_id: int, new_speed: FanSpeed) -> Dict:
        """
        AdjustWindSpeed(RoomId, NewSpeed)
        """
        room = self.rooms.get(room_id)
        if self.served_queue.contains(room_id):
            # 服务中直接更新风速与费率
            fee_rate = self.server.update_speed(room_id, new_speed)
            record_id = self.current_record_ids.get(room_id)
            if record_id is not None:
                self.detail_record.update_fee_rate(record_id, fee_rate, new_speed.name)
            return {
                "room_id": room_id,
                "state": "serving",
                "fan_speed": new_speed.name,
            }
        if self.waiting_queue.contains(room_id):
            # 等待队列中：若新风速更高，则提升排序并重置等待时间
            if new_speed.value > room.fan_speed.value:
                self.waiting_queue.promote(room_id)
                self.wait_timer.reset_timer(room_id)
            room.fan_speed = new_speed
            return {
                "room_id": room_id,
                "state": "waiting",
                "fan_speed": new_speed.name,
            }
        # 既不在服务也不在等待，视为未开机
        return {
            "room_id": room_id,
            "state": "off",
        }

    def power_off(self, room_id: int) -> None:
        room = self.rooms.get(room_id)
        if self.served_queue.contains(room_id):
            self.served_queue.pop(room_id)
        if self.waiting_queue.contains(room_id):
            self.waiting_queue.pop(room_id)
        room.state = PowerState.OFF
        # 结束当前详单记录
        record_id = self.current_record_ids.pop(room_id, None)
        if record_id is not None:
            totals = self.detail_record.get_room_total(room_id)
            self.detail_record.update_on_service(
                record_id,
                energy_used=totals["total_energy"],
                cost=totals["total_cost"],
                end_time=self._now_str(),
            )

    # ---------- 调度与时间推进 ----------
    def tick(self, delta_seconds: int) -> None:
        """
        每秒执行：更新计时器、温度、能耗、费用，并执行时间片调度与自动重启。
        """
        if delta_seconds <= 0:
            return

        for _ in range(delta_seconds):
            self._tick_one_second()

    def _tick_one_second(self) -> None:
        # 更新计时器
        self.service_timer.tick(1)
        self.wait_timer.tick(1)

        # 更新服务中房间的温度与能耗
        for room_id in self.served_queue.all_rooms():
            energy_used = self.server.update_temperature(room_id, 1)
            if energy_used > 0:
                totals = self.detail_record.get_room_total(room_id)
                record_id = self.current_record_ids.get(room_id)
                if record_id is not None:
                    self.detail_record.update_on_service(
                        record_id,
                        energy_used=totals["total_energy"],
                        cost=totals["total_cost"],
                    )

        # 时间片调度：等待时间达到 time_slice 的同风速请求轮转
        self._time_slice_schedule()

    def _time_slice_schedule(self) -> None:
        if self.time_slice <= 0:
            return
        # 简化实现：只根据等待时间 >= time_slice，将等待队列头部轮转进服务队列，
        # 并从服务队列中选择服务时间最长的房间暂停。
        ready_to_rotate: List[int] = []
        for room_id in self.waiting_queue.all_rooms():
            if self.wait_timer.get_wait_time(room_id) >= self.time_slice:
                ready_to_rotate.append(room_id)

        for room_id in ready_to_rotate:
            if not self.served_queue.all_rooms():
                continue
            # 找到服务时间最长的 victim
            victim = max(
                self.served_queue.all_rooms(),
                key=lambda rid: self.service_timer.get_service_time(rid),
            )
            # victim 暂停，进入等待；room_id 进入服务
            self.served_queue.pop(victim)
            self.waiting_queue.push(victim)
            self.rooms.get(victim).state = PowerState.WAITING
            self.served_queue.push(room_id)
            self.waiting_queue.pop(room_id)
            self.wait_timer.reset_timer(room_id)
            self.rooms.get(room_id).state = PowerState.SERVING

    # ---------- 查询与报表 ----------
    def get_room_status(self, room_id: int) -> Dict:
        room = self.rooms.get(room_id)
        totals = self.detail_record.get_room_total(room_id)
        return {
            "room_id": room.room_id,
            "mode": room.mode.value,
            "target_temp": room.target_temp,
            "current_temp": round(room.current_temp, 2),
            "fan_speed": room.fan_speed.name,
            "state": room.state.value,
            "energy_used": round(totals["total_energy"], 4),
            "cost": round(totals["total_cost"], 2),
            "served_seconds": self.service_timer.get_service_time(room_id),
            "waiting_seconds": self.wait_timer.get_wait_time(room_id),
        }

    def get_all_rooms_status(self) -> List[Dict]:
        return [self.get_room_status(r.room_id) for r in self.rooms.all()]

    def get_bill_for_room(self, room_id: int) -> Dict:
        totals = self.detail_record.get_room_total(room_id)
        details = self.detail_record.get_room_details(room_id)
        return {
            "room_id": room_id,
            "total_energy": round(totals["total_energy"], 4),
            "total_cost": round(totals["total_cost"], 2),
            "details": details,
        }

    def get_summary_report(self) -> Dict:
        summary = self.detail_record.get_summary()
        return {
            "total_energy": round(summary["total_energy"], 4),
            "total_cost": round(summary["total_cost"], 2),
        }

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class HotelACSystem:
    """
    对外的系统封装，便于 Flask / 前端调用。
    """

    def __init__(self, room_count: int, capacity: int, time_slice_seconds: int):
        self.rooms = RoomRepository(room_count)
        self.detail_record = DetailRecord()
        self.scheduler = Scheduler(
            rooms=self.rooms,
            capacity=capacity,
            time_slice_seconds=time_slice_seconds,
            detail_record=self.detail_record,
        )

    def tick(self, seconds: int) -> None:
        self.scheduler.tick(seconds)


