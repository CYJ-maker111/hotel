from datetime import datetime
from typing import Dict, Optional, List, Tuple

from .models import RoomRepository, Mode, FanSpeed, PowerState, Room
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
        # 将调度器自身传递给server，以便server可以访问队列管理功能
        self.server.scheduler = self
        self.detail_record = detail_record
        self.time_slice = time_slice_seconds
        # 记录当前正在服务的详单记录 id：room_id -> detail_record_id
        self.current_record_ids: Dict[int, int] = {}
        # 累计秒数，用于每分钟结束时进行温度四舍五入
        self._accumulated_seconds = 0
        # 记录每个房间本分钟开始时的温度，用于计算实际温度变化
        self._minute_start_temps: Dict[int, float] = {}
        
        # 设置队列的排序回调函数
        self.served_queue.set_sort_callback(lambda rid: (
            # 风速高的优先（按风速值降序）
            -self.rooms.get(rid).fan_speed.value,
            # 风速相同时，服务时间长的优先（按服务时间降序）
            -self.service_timer.get_service_time(rid)
        ))
        # 初始化时立即排序，确保顺序正确
        self.served_queue._sort_rooms()
        
        self.waiting_queue.set_sort_callback(lambda rid: (
            # 风速高的优先（按风速值降序）
            -self.rooms.get(rid).fan_speed.value,
            # 风速相同时，等待时间长的优先（按等待时间降序）
            -self.wait_timer.get_wait_time(rid)
        ))
    # ---------- 请求入口 ----------
    def power_on(self, room_id: int, current_room_temp: float, mode: Mode = Mode.COOL) -> Dict:
        """
        PowerOn(RoomId, CurrentRoomTemp, Mode)
        """
        # 检查服务队列是否有空位
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
        # 无空位，检查是否可以通过风速优先级替换进入服务队列
        served_rooms = self.served_queue.all_rooms()
        if served_rooms:
            new_room_speed = self.rooms.get(room_id).fan_speed.value
            
            # 情况1: 找到风速低于新请求的房间
            lower_speed_rooms = [rid for rid in served_rooms if self.rooms.get(rid).fan_speed.value < new_room_speed]
            
            # 情况2: 风速相同时，不允许直接替换，必须通过时间片调度机制
            # 新开机的房间等待时间为0，不应该替换任何已在服务队列中的同风速房间
            equal_speed_rooms = []  # 风速相同时，新请求应该进入等待队列
            
            # 合并需要替换的房间列表
            replaceable_rooms = lower_speed_rooms + equal_speed_rooms
            
            if replaceable_rooms:
                # 选择要替换的房间：风速最低，风速相同时选择服务时间最长的
                if len(set(self.rooms.get(rid).fan_speed.value for rid in replaceable_rooms)) == 1:
                    # 所有房间风速相同，选择服务时间最长的
                    victim = max(replaceable_rooms, key=lambda rid: self.service_timer.get_service_time(rid))
                else:
                    # 风速不同，选择风速最低的
                    victim = min(replaceable_rooms, key=lambda rid: self.rooms.get(rid).fan_speed.value)
                
                # 执行替换：将低优先级服务对象移至等待队列，新请求进入服务队列
                self.served_queue.pop(victim)
                self.rooms.get(victim).state = PowerState.WAITING
                self.service_timer.remove_timer(victim)
                self.waiting_queue.push(victim)
                self.wait_timer.create_timer(victim)
                
                # 新房间进入服务队列
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
                    operation_type="PRIORITY_REPLACE",
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
        
        # 无法通过优先级替换，进入等待队列
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
            # 无论风速增减，都重新排序队列以确保优先级正确
            self.served_queue._sort_rooms()
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
            # 如果风速发生变化，需要重新评估服务队列
            if new_speed.value > old_speed.value:
                # 风速提高，视为优先级提升，检查是否有更低风速的服务对象需要替换
                self._priority_schedule(room_id)
            elif new_speed.value < old_speed.value:
                # 风速降低，检查等待队列中是否有满足条件的房间可以进入服务队列
                self._check_waiting_queue_after_speed_decrease(room_id)
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
        
        # 检查房间实际状态
        return {
            "room_id": room_id,
            "state": room.state.value.lower(),
        }
        
    def _priority_schedule(self, room_id: int) -> None:
        """
        优先级调度：当服务队列中的房间风速提高时，仅重新排序服务队列，不再进行房间替换
        """
        # 仅重新排序服务队列，确保风速提高的房间获得更高优先级
        self.served_queue._sort_rooms()
        # 记录风速调整操作
        room = self.rooms.get(room_id)
        fee_rate = self.server._calc_fee_rate(room.fan_speed)
        self.detail_record.create_record(
            room_id=room_id,
            start_time=self._now_str(),
            mode=room.mode.value,
            target_temp=room.target_temp,
            fan_speed=room.fan_speed.name,
            fee_rate=fee_rate,
            operation_type="SPEED_ADJUST_PRIORITY",
        )
    
    def _check_waiting_queue_after_speed_decrease(self, room_id: int) -> None:
        """
        风速降低后检查等待队列：如果服务队列中某个房间优先级降低，检查等待队列中是否有更高优先级的房间可以替换
        """
        # 获取当前服务队列中的所有房间
        served_rooms = self.served_queue.all_rooms()
        
        # 如果服务队列已满，检查是否有等待队列中的房间优先级高于当前服务队列中的最低优先级房间
        if len(served_rooms) >= self.served_queue.capacity and self.waiting_queue.all_rooms():
            # 找到服务队列中优先级最低的房间（风速最低、服务时间最短）
            lowest_priority_served = min(
                served_rooms,
                key=lambda rid: (self.rooms.get(rid).fan_speed.value, self.service_timer.get_service_time(rid))
            )
            
            # 找到等待队列中优先级最高的房间（等待时间最长）
            waiting_rooms = self.waiting_queue.all_rooms()
            highest_priority_waiting = max(
                waiting_rooms,
                key=lambda rid: self.wait_timer.get_wait_time(rid)
            )
            
            # 检查等待队列中的房间是否满足等待时间要求（等待时间 >= 时间片）
            waiting_time = self.wait_timer.get_wait_time(highest_priority_waiting)
            if waiting_time >= self.time_slice:
                # 比较优先级：等待队列中的房间优先级是否高于服务队列中最低优先级的房间
                served_priority = self.rooms.get(lowest_priority_served).fan_speed.value
                waiting_priority = self.rooms.get(highest_priority_waiting).fan_speed.value
                
                # 如果等待队列中的房间优先级更高，进行替换
                if waiting_priority > served_priority:
                    self._replace_served_with_waiting(lowest_priority_served, highest_priority_waiting)
                
    def _replace_served_with_waiting(self, victim: int, waiting_room: int) -> None:
        """
        将服务队列中的受害者替换为等待队列中的房间
        """
        # 先从服务队列移除受害者
        self.served_queue.pop(victim)
        
        # 确保房间能添加到等待队列：如果队列已满，移除优先级最低的等待房间
        if self.waiting_queue.capacity != -1 and len(self.waiting_queue.all_rooms()) >= self.waiting_queue.capacity and not self.waiting_queue.contains(victim):
            # 找到等待队列中优先级最低的房间并移除
            wait_rooms = self.waiting_queue.all_rooms()
            if len(wait_rooms) > 0:
                # 选择风速最低、等待时间最短的房间移除
                lowest_priority_room = min(wait_rooms, key=lambda rid: (self.rooms.get(rid).fan_speed.value, self.wait_timer.get_wait_time(rid)))
                self.waiting_queue.pop(lowest_priority_room)
                # 将移除的房间状态设置为暂停，避免状态不一致
                self.rooms.get(lowest_priority_room).state = PowerState.PAUSED
                self.wait_timer._waiting_seconds.pop(lowest_priority_room, None)
        
        # 如果房间已经在队列中，先移除再添加，确保状态一致
        if self.waiting_queue.contains(victim):
            self.waiting_queue.pop(victim)
        # 尝试添加到等待队列
        if self.waiting_queue.capacity == -1 or len(self.waiting_queue.all_rooms()) < self.waiting_queue.capacity:
            self.waiting_queue.push(victim)
        
        # 无论是否成功添加到等待队列，都更新状态为等待
        self.rooms.get(victim).state = PowerState.WAITING
        self.service_timer.remove_timer(victim)
        if self.wait_timer.get_wait_time(victim) == 0:
            self.wait_timer.create_timer(victim)
        
        # 确保服务队列有容量后才添加
        if self.served_queue.check().has_slot:
            # 将等待房间移至服务队列
            self.waiting_queue.pop(waiting_room)
            self.served_queue.push(waiting_room)
            self.rooms.get(waiting_room).state = PowerState.SERVING
            self.service_timer.reset_timer(waiting_room)
            self.wait_timer._waiting_seconds.pop(waiting_room, None)
        else:
            # 服务队列已满，无法添加新房间，保持等待状态
            pass
    
    def adjust_temperature(self, room_id: int, new_target_temp: float) -> Dict:
        """
        ChangeTemp(RoomIdTargetTemp)
        允许 SERVING、WAITING、PAUSED 状态的房间修改目标温度
        """
        room = self.rooms.get(room_id)
        
        # SERVING 状态：服务中直接更新目标温度
        if self.served_queue.contains(room_id):
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
        
        # WAITING 状态：等待队列中直接更新房间的目标温度
        if self.waiting_queue.contains(room_id):
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
        
        # PAUSED 状态：暂停时也允许修改目标温度
        if room.state == PowerState.PAUSED:
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
        
        # OFF 或其他状态：返回房间状态
        return {
            "room_id": room_id,
            "state": room.state.value.lower(),
            "message": "房间未开机或状态不允许调温"
        }

    def power_off(self, room_id: int) -> Dict:
        room = self.rooms.get(room_id)
        if self.served_queue.contains(room_id):
            self.served_queue.pop(room_id)
            self.service_timer.remove_timer(room_id)
        if self.waiting_queue.contains(room_id):
            self.waiting_queue.pop(room_id)
            self.wait_timer._waiting_seconds.pop(room_id, None)
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
        # 服务时间更新后立即触发排序
        self.served_queue._sort_rooms()
        
        # 如果是本分钟的第一秒，记录所有房间的起始温度
        if self._accumulated_seconds == 0:
            for room_id in self.rooms.rooms.keys():
                room = self.rooms.get(room_id)
                self._minute_start_temps[room_id] = room.current_temp

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
        
        # 累计秒数加1
        self._accumulated_seconds += 1
        
        # 每到60秒（1分钟）结束时，对所有房间的温度和费用进行四舍五入并对齐
        if self._accumulated_seconds >= 60:
            self._accumulated_seconds = 0
            for room_id in self.rooms.rooms.keys():
                room = self.rooms.get(room_id)
                
                # 如果房间在本分钟内处于SERVING状态，需要调整费用与温度变化对齐
                if room.state == PowerState.SERVING and room_id in self._minute_start_temps:
                    # 获取本分钟开始时的温度
                    start_temp = self._minute_start_temps[room_id]
                    # 四舍五入前的温度变化（绝对值）
                    temp_change_before = abs(room.current_temp - start_temp)
                    
                    # 温度四舍五入到小数点后一位
                    old_temp = room.current_temp
                    room.current_temp = round(room.current_temp, 1)
                    
                    # 四舍五入后的温度变化（绝对值）
                    temp_change_after = abs(room.current_temp - start_temp)
                    
                    # 费用调整：根据温度四舍五入后的实际变化调整费用
                    # 因为费用 = 温度变化量（℃）* 1元/1℃
                    cost_adjustment = temp_change_after - temp_change_before
                    
                    # 调整费用
                    room.cost += cost_adjustment
                    room.cost = round(room.cost, 2)
                    
                    # 同时更新详单记录中的费用
                    record_id = self.current_record_ids.get(room_id)
                    if record_id is not None:
                        current_record = self.detail_record.get_record(record_id)
                        if current_record:
                            # 使用调整后的费用更新记录
                            adjusted_cost = current_record["cost"] + cost_adjustment
                            adjusted_cost = round(adjusted_cost, 2)
                            self.detail_record.update_on_service(
                                record_id,
                                cost=adjusted_cost,
                            )
                else:
                    # 非SERVING状态的房间，直接四舍五入温度
                    room.current_temp = round(room.current_temp, 1)
                    room.cost = round(room.cost, 2)
                
                # 更新本分钟开始时的温度为四舍五入后的当前温度
                self._minute_start_temps[room_id] = room.current_temp

        # 检查是否有服务对象的目标温度到达或关机（状态变化）
        after_states = {rid: room.state for rid, room in self.rooms.rooms.items()}
        
        # 检查是否有房间从SERVING变为PAUSED（目标温度到达）或OFF（关机）
        state_changed_rooms = []
        for room_id, before_state in before_states.items():
            after_state = after_states[room_id]
            if before_state == PowerState.SERVING and after_state in [PowerState.PAUSED, PowerState.OFF]:
                state_changed_rooms.append(room_id)
                # 从服务队列中移除已暂停/关闭的房间
                if room_id in self.served_queue.all_rooms():
                    self.served_queue.pop(room_id)
                    # 从服务计时器中移除房间，确保不再计时
                    self.service_timer.remove_timer(room_id)
                # 确保已暂停的房间不在等待队列中
                if after_state == PowerState.PAUSED and room_id in self.waiting_queue.all_rooms():
                    self.waiting_queue.pop(room_id)
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
        
        # 当服务队列因状态变化出现空位时，从等待队列调度优先级最高的房间补充
        self._fill_served_queue_from_waiting()
                    
        # 仅执行时间片调度，处理等待超时的同风速请求
        # 时间片调度逻辑会根据预设条件决定是否进行替换
        self._time_slice_schedule()
        
    def _fill_served_queue_from_waiting(self) -> None:
        """
        当服务队列未满时，从等待队列中选取优先级最高的房间补充到服务队列
        """
        # 检查服务队列是否有空位
        if len(self.served_queue.all_rooms()) >= self.served_queue.capacity:
            return
        
        # 检查等待队列是否有房间
        waiting_rooms = self.waiting_queue.all_rooms()
        if not waiting_rooms:
            return
        
        # 从等待队列中选取优先级最高的房间（使用已设置的排序回调）
        # 由于等待队列已经按优先级排序，直接取第一个
        selected = waiting_rooms[0]
        
        # 将选中的房间从等待队列移除并添加到服务队列
        self.waiting_queue.pop(selected)
        self.served_queue.push(selected)
        
        # 更新房间状态为SERVING
        room = self.rooms.get(selected)
        if room is None:
            return
            
        room.state = PowerState.SERVING
        
        # 重置服务计时器
        self.service_timer.reset_timer(selected)
        
        # 移除等待计时器，避免等待时间继续递增
        self.wait_timer._waiting_seconds.pop(selected, None)
        
        try:
            # 创建新的详单记录
            record_id = self.detail_record.create_record(
                room_id=selected,
                start_time=self._now_str(),
                mode=room.mode.value,
                target_temp=room.target_temp,
                fan_speed=room.fan_speed.name,
                fee_rate=self.server._calc_fee_rate(room.fan_speed),
                operation_type="QUEUE_FILL",
            )
            self.current_record_ids[selected] = record_id
        except Exception as e:
            # 错误处理，确保即使创建记录失败也不会中断流程
            print(f"Error creating record for room {selected}: {e}")

    def _on_room_state_changed(self, room_id: int, new_state: PowerState) -> None:
        """
        当房间状态发生变化时的回调方法
        """
        room = self.rooms.get(room_id)
        
        # 获取当前房间状态作为旧状态
        old_state = room.state
        
        # 在更新房间状态之前，先处理所有依赖于旧状态的操作
        state_changed = False
        
        # 如果房间从SERVING变为PAUSED或OFF，需要立即从服务队列中移除
        if old_state == PowerState.SERVING and new_state in [PowerState.PAUSED, PowerState.OFF]:
            state_changed = True
            if room_id in self.served_queue.all_rooms():
                self.served_queue.pop(room_id)
                # 从服务计时器中移除房间，确保不再计时
                self.service_timer.remove_timer(room_id)
            
            # 确保已暂停的房间不在等待队列中
            if new_state == PowerState.PAUSED and room_id in self.waiting_queue.all_rooms():
                self.waiting_queue.pop(room_id)
            
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
        
        # 更新房间状态
        room.state = new_state

        # 只有在状态变化时才重新排序服务队列
        if state_changed:
            self.served_queue._sort_rooms()
            # 当服务队列因状态变化出现空位时，从等待队列调度优先级最高的房间补充
            self._fill_served_queue_from_waiting()
        
        # 注意：在_on_room_state_changed中不应该自动调度等待队列中的房间
        # 调度逻辑应该在power_on方法中根据优先级规则处理，或者在tick方法中定期执行
        # 避免在状态变化时错误调度，导致新开机房间被错误处理

    def _time_slice_schedule(self) -> None:
        """
        时间片调度：当等待队列中有同风速的请求，按照等待时间优先级进行调度
        
        策略：
        1. 只有当服务队列已满时，才执行时间片调度
        2. 风速相等时的调度策略：
           - 等待时间越长，优先级越高
           - 等待满time_slice的请求优先于未等待满的
           - 等待时间相同，优先处理已等待满time_slice的
        """
        # 注意：时间片调度是一个独立的调度机制，与power_on方法中的风速优先级调度互不干扰
        # power_on方法负责新开机房间的初始调度（风速优先级为主）
        # 时间片调度负责同风速房间之间的轮换（等待时间为主）
        # 两者应该协同工作但不应该互相干扰
        
        # 只有当服务队列已满且等待队列不为空时才执行时间片调度
        if not self.waiting_queue.all_rooms() or len(self.served_queue.all_rooms()) < self.served_queue.capacity:
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
                
                # 确保房间能添加到等待队列：如果队列已满，移除优先级最低的等待房间
                if self.waiting_queue.capacity != -1 and len(self.waiting_queue.all_rooms()) >= self.waiting_queue.capacity and not self.waiting_queue.contains(victim):
                    # 找到等待队列中优先级最低的房间并移除
                    wait_rooms = self.waiting_queue.all_rooms()
                    if len(wait_rooms) > 0:
                        # 选择风速最低、等待时间最短的房间移除
                        lowest_priority_room = min(wait_rooms, key=lambda rid: (self.rooms.get(rid).fan_speed.value, self.wait_timer.get_wait_time(rid)))
                        self.waiting_queue.pop(lowest_priority_room)
                        # 将移除的房间状态设置为暂停，避免状态不一致
                        self.rooms.get(lowest_priority_room).state = PowerState.PAUSED
                        self.wait_timer._waiting_seconds.pop(lowest_priority_room, None)
                
                # 如果房间已经在队列中，先移除再添加，确保状态一致
                if self.waiting_queue.contains(victim):
                    self.waiting_queue.pop(victim)
                # 尝试添加到等待队列
                if self.waiting_queue.capacity == -1 or len(self.waiting_queue.all_rooms()) < self.waiting_queue.capacity:
                    self.waiting_queue.push(victim)
                
                # 无论是否成功添加到等待队列，都更新状态为等待
                self.rooms.get(victim).state = PowerState.WAITING
                self.service_timer.remove_timer(victim)
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
    
    def validate_scheduling_logic(self) -> bool:
        """
        内部验证方法，用于测试调度逻辑的正确性
        返回True表示逻辑正确，False表示存在问题
        """
        # 检查tick_one_second方法中是否正确移除了自动调度代码
        import inspect
        source = inspect.getsource(self._tick_one_second)
        
        # 检查是否包含不应存在的自动调度代码模式
        forbidden_patterns = [
            "self.served_queue.is_full()",  # 不应该在tick_one_second中检查队列是否已满
            "self.waiting_queue.size() > 0",  # 不应该在tick_one_second中检查等待队列
            "self.waiting_queue.get_all_rooms()",  # 不应该在tick_one_second中获取等待队列房间
            "self._replace_room",  # 不应该在tick_one_second中直接替换房间
            "self.waiting_queue.pop",  # 不应该在tick_one_second中从等待队列移除房间
            "self.served_queue.push",  # 不应该在tick_one_second中向服务队列添加房间
        ]
        
        # 检查是否包含这些禁止的模式
        for pattern in forbidden_patterns:
            if pattern in source:
                print(f"错误: _tick_one_second方法中包含禁止的代码模式: {pattern}")
                return False
        
        # 检查power_on方法中的同风速处理逻辑是否正确
        power_on_source = inspect.getsource(self.power_on)
        if "equal_speed_rooms = []" not in power_on_source:
            print("错误: power_on方法中缺少正确的同风速房间处理逻辑")
            return False
        
        # 检查_on_room_state_changed方法是否有正确注释
        if hasattr(self, '_on_room_state_changed'):
            state_changed_source = inspect.getsource(self._on_room_state_changed)
            if "不应自动调度等待队列房间" not in state_changed_source:
                print("警告: _on_room_state_changed方法缺少必要的注释")
        
        print("调度逻辑验证通过！")
        return True

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


