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
        served_capacity: int,
        waiting_capacity: int,
        time_slice_seconds: int,
        detail_record: DetailRecord,
    ):
        self.rooms = rooms
        self.served_queue = ServedQueue(served_capacity)
        self.waiting_queue = WaitingQueue(waiting_capacity)
        self.service_timer = ServiceTimer()
        self.wait_timer = WaitTimer()
        self.server = Server(rooms)
        self.detail_record = detail_record
        self.time_slice = time_slice_seconds
        # 记录当前正在服务的详单记录 id：room_id -> detail_record_id
        self.current_record_ids: Dict[int, int] = {}

    # ---------- 请求入口 ----------
    def power_on(self, room_id: int, current_room_temp: float, mode: Mode = Mode.COOL) -> Dict:
        """
        PowerOn(RoomId, CurrentRoomTemp, Mode)
        """
        state = self.served_queue.check()
        if state.has_slot:
            # 进入服务队列
            self.served_queue.push(room_id)
            mode, target_temp, fee_rate = self.server.set_target(room_id, current_room_temp, mode)
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
        room.current_temp = current_room_temp
        room.mode = mode
        return {
            "room_id": room_id,
            "state": "waiting",
        }

    def adjust_wind_speed(self, room_id: int, new_speed: FanSpeed) -> Dict:
        """
        ChangeSpeed(RoomIdFanSpeed)
        """
        room = self.rooms.get(room_id)
        old_speed = room.fan_speed
        room.fan_speed = new_speed
        
        if self.served_queue.contains(room_id):
            # 服务中更新风速与费率
            fee_rate = self.server.update_speed(room_id, new_speed)
            
            # 如果风速发生变化，结束当前记录并创建新记录
            if old_speed != new_speed:
                record_id = self.current_record_ids.get(room_id)
                if record_id is not None:
                    # 结束当前记录
                    current_record = self.detail_record.get_record(record_id)
                    if current_record:
                        self.detail_record.update_on_service(
                            record_id,
                            cost=current_record["cost"],
                            end_time=self._now_str(),
                        )
                    # 创建新记录
                    new_record_id = self.detail_record.create_record(
                        room_id=room_id,
                        start_time=self._now_str(),
                        mode=room.mode.value,
                        target_temp=room.target_temp,
                        fan_speed=new_speed.name,
                        fee_rate=fee_rate,
                        operation_type="SPEED_CHANGE",
                    )
                    self.current_record_ids[room_id] = new_record_id
            # 如果风速提高，需要重新评估服务队列
            if new_speed.value > old_speed.value:
                # 风速提高，视为优先级提升，检查是否有更低风速的服务对象需要替换
                self._priority_schedule(room_id)
            return {"ok": "SOk"}
        
        if self.waiting_queue.contains(room_id):
            # 等待队列中更新风速
            if new_speed.value > old_speed.value:
                self.waiting_queue.promote(room_id)
                self.wait_timer.reset_timer(room_id)
            
            # 检查服务队列是否有可以被替换的房间（优先级调度策略）
            served_rooms = self.served_queue.all_rooms()
            if served_rooms:
                # 计算有多少个服务对象的风速低于请求风速
                lower_speed_rooms = [rid for rid in served_rooms if self.rooms.get(rid).fan_speed.value < new_speed.value]
                
                if lower_speed_rooms:
                    # 2.1.1 如果只有1个风速低于的服务对象
                    if len(lower_speed_rooms) == 1:
                        victim = lower_speed_rooms[0]
                    # 2.1.2 如果有多个服务对象的风速相等且低于请求对象
                    elif len(set(self.rooms.get(rid).fan_speed.value for rid in lower_speed_rooms)) == 1:
                        # 选择服务时长最大的服务对象
                        victim = max(lower_speed_rooms, key=lambda rid: self.service_timer.get_service_time(rid))
                    # 2.1.3 如果多个服务对象的风速低于请求风速，且风速不相等
                    else:
                        # 选择风速最低的服务对象
                        victim = min(lower_speed_rooms, key=lambda rid: self.rooms.get(rid).fan_speed.value)
                    
                    # 执行替换
                    self._replace_served_with_waiting(victim, room_id)
                    
                    # 更新风速与费率
                    fee_rate = self.server.update_speed(room_id, new_speed)
                    record_id = self.current_record_ids.get(room_id)
                    if record_id is not None:
                        self.detail_record.update_fee_rate(record_id, fee_rate, new_speed.name)
            
            return {"ok": "SOk"}
        
        # 既不在服务也不在等待，视为未开机
        return {
            "room_id": room_id,
            "state": "off",
        }
        
    def _priority_schedule(self, room_id: int) -> None:
        """
        优先级调度：当服务队列中的房间风速提高时，检查是否有更低风速的服务对象需要替换
        """
        room = self.rooms.get(room_id)
        new_speed = room.fan_speed
        
        # 计算有多少个服务对象的风速低于当前房间风速
        served_rooms = self.served_queue.all_rooms()
        lower_speed_rooms = [rid for rid in served_rooms if rid != room_id and self.rooms.get(rid).fan_speed.value < new_speed.value]
        
        if lower_speed_rooms:
            # 2.1.1 如果只有1个风速低于的服务对象
            if len(lower_speed_rooms) == 1:
                victim = lower_speed_rooms[0]
            # 2.1.2 如果有多个服务对象的风速相等且低于请求对象
            elif len(set(self.rooms.get(rid).fan_speed.value for rid in lower_speed_rooms)) == 1:
                # 选择服务时长最大的服务对象
                victim = max(lower_speed_rooms, key=lambda rid: self.service_timer.get_service_time(rid))
            # 2.1.3 如果多个服务对象的风速低于请求风速，且风速不相等
            else:
                # 选择风速最低的服务对象
                victim = min(lower_speed_rooms, key=lambda rid: self.rooms.get(rid).fan_speed.value)
            
            # 执行替换：将受害者移到等待队列
            self.waiting_queue.push(victim)
            self.served_queue.pop(victim)
            self.rooms.get(victim).state = PowerState.WAITING
            self.service_timer.reset_timer(victim)
            if self.wait_timer.get_wait_time(victim) == 0:
                self.wait_timer.create_timer(victim)
            
            # 检查服务队列是否有空位，如果有，从等待队列中选择优先级最高的房间填充
            if self.waiting_queue.all_rooms():
                # 从等待队列中选择等待时间最久的房间
                waiting_rooms = self.waiting_queue.all_rooms()
                selected = max(
                    waiting_rooms,
                    key=lambda rid: self.wait_timer.get_wait_time(rid)
                )
                
                # 将选中的房间从等待队列移至服务队列
                self.waiting_queue.pop(selected)
                self.served_queue.push(selected)
                self.rooms.get(selected).state = PowerState.SERVING
                self.service_timer.reset_timer(selected)
                self.wait_timer._waiting_seconds.pop(selected, None)
                
                # 更新服务队列的详单记录
                fee_rate = self.server._calc_fee_rate(self.rooms.get(selected).fan_speed)
                record_id = self.current_record_ids.get(selected)
                if record_id is None:
                    record_id = self.detail_record.create_record(
                        room_id=selected,
                        start_time=self._now_str(),
                        mode=self.rooms.get(selected).mode.value,
                        target_temp=self.rooms.get(selected).target_temp,
                        fan_speed=self.rooms.get(selected).fan_speed.name,
                        fee_rate=fee_rate,
                        operation_type="SERVING_RESUME",
                    )
                    self.current_record_ids[selected] = record_id
                else:
                    self.detail_record.update_fee_rate(record_id, fee_rate, self.rooms.get(selected).fan_speed.name)
                
    def _replace_served_with_waiting(self, victim: int, waiting_room: int) -> None:
        """
        将服务队列中的受害者替换为等待队列中的房间
        """
        # 从服务队列移除受害者
        self.served_queue.pop(victim)
        self.waiting_queue.push(victim)
        self.rooms.get(victim).state = PowerState.WAITING
        self.service_timer.reset_timer(victim)
        if self.wait_timer.get_wait_time(victim) == 0:
            self.wait_timer.create_timer(victim)
        
        # 将等待房间移至服务队列
        self.waiting_queue.pop(waiting_room)
        self.served_queue.push(waiting_room)
        self.rooms.get(waiting_room).state = PowerState.SERVING
        self.service_timer.reset_timer(waiting_room)
        self.wait_timer._waiting_seconds.pop(waiting_room, None)
    
    def adjust_temperature(self, room_id: int, new_target_temp: float) -> Dict:
        """
        ChangeTemp(RoomIdTargetTemp)
        """
        room = self.rooms.get(room_id)
        if self.served_queue.contains(room_id):
            # 服务中直接更新目标温度
            self.server.update_target_temperature(room_id, new_target_temp)
            # 创建一条新的详单记录，记录温度变化事件
            self.detail_record.create_record(
                room_id=room_id,
                start_time=self._now_str(),
                mode=room.mode.value,
                target_temp=new_target_temp,
                fan_speed=room.fan_speed.name,
                fee_rate=self.server._calc_fee_rate(room.fan_speed),
                operation_type="TEMP_CHANGE",
            )
            return {"ok": "SOk"}
        if self.waiting_queue.contains(room_id):
            # 等待队列中直接更新房间的目标温度（不通过服务器，因为未服务）
            room.target_temp = new_target_temp
            # 创建一条新的详单记录，记录温度变化事件
            self.detail_record.create_record(
                room_id=room_id,
                start_time=self._now_str(),
                mode=room.mode.value,
                target_temp=new_target_temp,
                fan_speed=room.fan_speed.name,
                fee_rate=self.server._calc_fee_rate(room.fan_speed),
                operation_type="TEMP_CHANGE",
            )
            return {"ok": "SOk"}
        # 既不在服务也不在等待，视为未开机
        return {
            "room_id": room_id,
            "state": "off",
        }

    def power_off(self, room_id: int) -> Dict:
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
                cost=totals["total_cost"],
                end_time=self._now_str(),
            )
        
        # 获取当前费用和总费用
        totals = self.detail_record.get_room_total(room_id)
        return {
            "room_id": room_id,
            "state": "off",
            "current_fee": totals["total_cost"],
            "total_fee": totals["total_cost"]
        }

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

        # 记录服务状态变化（用于检测目标温度到达）
        before_states = {rid: room.state for rid, room in self.rooms.rooms.items()}

        # 更新所有房间的温度与费用（包括服务中、暂停和关机状态）
        for room_id in self.rooms.rooms.keys():
            room = self.rooms.get(room_id)
            cost = self.server.update_temperature(room_id, 1)
            if cost > 0:
                # 只有SERVING状态会产生费用
                if room.state == PowerState.SERVING:
                    # 更新房间的费用
                    room.cost += cost
                    
                    # 更新当前详单记录
                    record_id = self.current_record_ids.get(room_id)
                    if record_id is not None:
                        # 直接使用当前计算的费用更新记录
                        # 先获取当前记录的费用
                        current_record = self.detail_record.get_record(record_id)
                        if current_record:
                            new_cost = current_record["cost"] + cost
                            self.detail_record.update_on_service(
                                record_id,
                                cost=new_cost,
                            )

        # 检查是否有服务对象的目标温度到达或关机（状态变化）
        after_states = {rid: room.state for rid, room in self.rooms.rooms.items()}
        
        # 检查是否有房间从SERVING变为PAUSED（目标温度到达）或OFF（关机）
        state_changed_rooms = []
        for room_id, before_state in before_states.items():
            after_state = after_states[room_id]
            if before_state == PowerState.SERVING and after_state in [PowerState.PAUSED, PowerState.OFF]:
                state_changed_rooms.append(room_id)
                # 为状态变化的房间设置详单记录结束时间
                record_id = self.current_record_ids.get(room_id)
                if record_id is not None:
                    # 获取当前记录的费用
                    current_record = self.detail_record.get_record(record_id)
                    if current_record:
                        self.detail_record.update_on_service(
                            record_id,
                            cost=current_record["cost"],
                            end_time=self._now_str(),
                        )
                    # 从当前记录ID字典中移除
                    self.current_record_ids.pop(room_id, None)
        
        # 如果有服务对象释放，让等待队列中的等待服务时长最久的对象获得服务（2.2.3）
        if state_changed_rooms and self.waiting_queue.all_rooms():
            # 从等待队列中选择等待时间最久的房间
            waiting_rooms = self.waiting_queue.all_rooms()
            selected = max(
                waiting_rooms,
                key=lambda rid: self.wait_timer.get_wait_time(rid)
            )
            
            # 将选中的房间从等待队列移至服务队列
            self.waiting_queue.pop(selected)
            self.served_queue.push(selected)
            self.rooms.get(selected).state = PowerState.SERVING
            self.service_timer.reset_timer(selected)
            self.wait_timer._waiting_seconds.pop(selected, None)
            
            # 为新进入服务的房间创建新的详单记录
            room = self.rooms.get(selected)
            fee_rate = self.server._calc_fee_rate(room.fan_speed)
            record_id = self.detail_record.create_record(
                room_id=selected,
                start_time=self._now_str(),
                mode=room.mode,
                target_temp=room.target_temp,
                fan_speed=room.fan_speed.name,
                fee_rate=fee_rate,
                operation_type="SERVING_RESUME",
            )
            self.current_record_ids[selected] = record_id

        # 时间片调度：等待时间达到 time_slice 的同风速请求轮转
        self._time_slice_schedule()

    def _time_slice_schedule(self) -> None:
        """
        时间片调度：当等待队列中有同风速的请求，按照等待时间优先级进行调度
        
        策略：
        1. 2.2.1-2.2.4：风速相等时的调度策略
           - 等待时间越长，优先级越高
           - 等待满time_slice的请求优先于未等待满的
           - 等待时间相同，优先处理已等待满time_slice的
        """
        if not self.waiting_queue.all_rooms() or len(self.served_queue.all_rooms()) == 0:
            return

        # 获取服务队列的风速分布
        served_speeds = set()
        for room_id in self.served_queue.all_rooms():
            served_speeds.add(self.rooms.get(room_id).fan_speed)

        # 检查是否存在同风速的等待请求
        for speed in served_speeds:
            # 收集服务队列中该风速的房间
            served_rooms = [rid for rid in self.served_queue.all_rooms() if self.rooms.get(rid).fan_speed == speed]
            if not served_rooms:
                continue

            # 收集等待队列中该风速的房间
            waiting_rooms = [
                rid for rid in self.waiting_queue.all_rooms() 
                if self.rooms.get(rid).fan_speed == speed
            ]
            if not waiting_rooms:
                continue

            # 对等待房间进行优先级排序：
            # 1. 等待满time_slice的优先于未等待满的
            # 2. 等待时间越长，优先级越高
            def waiting_priority(rid):
                wait_time = self.wait_timer.get_wait_time(rid)
                is_waited_full = wait_time >= self.time_slice
                return (is_waited_full, wait_time)  # (布尔值，等待时间)，布尔值True的优先级高于False

            # 选择优先级最高的等待房间
            selected = max(waiting_rooms, key=waiting_priority)
            selected_wait_time = self.wait_timer.get_wait_time(selected)

            # 如果等待时间达到或超过time_slice，执行替换（2.2.2）
            if selected_wait_time >= self.time_slice:
                # 从服务队列中选择服务时长最大的房间
                victim = max(served_rooms, key=lambda rid: self.service_timer.get_service_time(rid))

                # 执行替换
                self.served_queue.pop(victim)
                self.waiting_queue.push(victim)
                self.rooms.get(victim).state = PowerState.WAITING
                self.service_timer.reset_timer(victim)
                # 分配等待服务时长s秒（2.2.2）
                self.wait_timer.reset_timer(victim)  # 重置为0，开始新的等待周期
                if victim not in self.wait_timer._waiting_seconds:
                    self.wait_timer.create_timer(victim)
                
                # selected 进入服务（2.2.2）
                self.served_queue.push(selected)
                self.waiting_queue.pop(selected)
                self.rooms.get(selected).state = PowerState.SERVING
                self.service_timer.reset_timer(selected)
                # 当房间进入服务队列时，移除等待计时器，避免等待时间继续递增
                self.wait_timer._waiting_seconds.pop(selected, None)

                break  # 每次只执行一次替换

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
            "cost": round(room.cost, 2),
            "served_seconds": self.service_timer.get_service_time(room_id),
            "waiting_seconds": self.wait_timer.get_wait_time(room_id),
        }

    def get_all_rooms_status(self) -> List[Dict]:
        return [self.get_room_status(r.room_id) for r in self.rooms.all()]
        
    def request_number_service_number(self, room_id: int) -> Dict:
        """
        RequestNumberServiceNumber
        """
        if self.waiting_queue.contains(room_id):
            list_number = self.waiting_queue.get_position(room_id) + 1  # 队列位置从1开始
            return {
                "state": "wait",
                "list_number": list_number
            }
        return {
            "state": self.rooms.get(room_id).state.name.lower()
        }
        
    def request_state(self, room_id: int) -> Dict:
        """
        RequestState(RoomId)
        """
        totals = self.detail_record.get_room_total(room_id)
        return {
            "current_fee": totals["total_cost"],
            "total_fee": totals["total_cost"]
        }

    def get_bill_for_room(self, room_id: int) -> Dict:
        totals = self.detail_record.get_room_total(room_id)
        details = self.detail_record.get_room_details(room_id)
        return {
            "room_id": room_id,
            "total_cost": round(totals["total_cost"], 2),
            "details": details,
        }

    def get_served_queue(self) -> List[int]:
        """
        获取当前服务队列中的所有房间ID
        """
        return self.served_queue.all_rooms()

    def get_waiting_queue(self) -> List[int]:
        """
        获取当前等待队列中的所有房间ID
        """
        return self.waiting_queue.all_rooms()

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

    def __init__(self, room_count: int, served_capacity: int, waiting_capacity: int, time_slice_seconds: int):
        self.rooms = RoomRepository(room_count)
        self.detail_record = DetailRecord()
        self.scheduler = Scheduler(
            rooms=self.rooms,
            served_capacity=served_capacity,
            waiting_capacity=waiting_capacity,
            time_slice_seconds=time_slice_seconds,
            detail_record=self.detail_record,
        )

    def tick(self, seconds: int) -> None:
        self.scheduler.tick(seconds)

    def clear_all_records(self):
        """
        清除所有房间的详单记录。
        """
        self.detail_record.clear_all_records()


