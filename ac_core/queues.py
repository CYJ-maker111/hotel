from typing import List


class ServiceState:
    def __init__(self, has_slot: bool):
        self.has_slot = has_slot


class ServedQueue:
    """
    服务队列：维护当前正在送风的房间 ID 列表
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._rooms: List[int] = []

    def check(self) -> ServiceState:
        return ServiceState(has_slot=len(self._rooms) < self.capacity)

    def push(self, room_id: int) -> None:
        if room_id not in self._rooms and len(self._rooms) < self.capacity:
            self._rooms.append(room_id)

    def pop(self, room_id: int) -> None:
        if room_id in self._rooms:
            self._rooms.remove(room_id)

    def contains(self, room_id: int) -> bool:
        return room_id in self._rooms

    def all_rooms(self) -> List[int]:
        return list(self._rooms)


class WaitingQueue:
    """
    等待队列：按顺序维护等待服务的房间 ID 列表
    """

    def __init__(self):
        self._rooms: List[int] = []

    def push(self, room_id: int) -> None:
        if room_id not in self._rooms:
            self._rooms.append(room_id)

    def pop(self, room_id: int) -> None:
        if room_id in self._rooms:
            self._rooms.remove(room_id)

    def promote(self, room_id: int) -> None:
        """
        提前排队序号：用于高风速时的优先调度
        """
        if room_id in self._rooms:
            self._rooms.remove(room_id)
            self._rooms.insert(0, room_id)

    def contains(self, room_id: int) -> bool:
        return room_id in self._rooms

    def all_rooms(self) -> List[int]:
        return list(self._rooms)


