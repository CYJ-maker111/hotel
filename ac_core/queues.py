from typing import List


class ServiceState:
    def __init__(self, has_slot: bool):
        self.has_slot = has_slot


class ServedQueue:
    """
    服务队列：维护当前正在送风的房间 ID 列表，按优先级排序
    优先级：风速(高->低) > 服务时间(长->短)
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._rooms: List[int] = []
        self._sort_callback = None

    def set_sort_callback(self, callback):
        """
        设置排序回调函数，用于确定房间的优先级
        """
        self._sort_callback = callback
        self._sort_rooms()

    def _sort_rooms(self):
        """
        根据排序回调函数对房间进行排序
        """
        if self._sort_callback and len(self._rooms) > 0:
            self._rooms.sort(key=self._sort_callback)

    def check(self) -> ServiceState:
        return ServiceState(has_slot=len(self._rooms) < self.capacity)

    def push(self, room_id: int) -> None:
        if room_id not in self._rooms and len(self._rooms) < self.capacity:
            self._rooms.append(room_id)
            self._sort_rooms()

    def pop(self, room_id: int) -> None:
        if room_id in self._rooms:
            self._rooms.remove(room_id)
            # 移除房间后需要重新排序
            self._sort_rooms()

    def contains(self, room_id: int) -> bool:
        return room_id in self._rooms

    def all_rooms(self) -> List[int]:
        return list(self._rooms)


class WaitingQueue:
    """
    等待队列：按顺序维护等待服务的房间 ID 列表
    """

    def __init__(self, capacity: int = -1):
        """
        初始化等待队列
        capacity: 队列容量，-1表示无界
        """
        self._rooms: List[int] = []
        self.capacity = capacity
        self._sort_callback = None

    def set_sort_callback(self, callback):
        """
        设置排序回调函数，用于确定房间的优先级
        """
        self._sort_callback = callback
        self._sort_rooms()

    def _sort_rooms(self):
        """
        根据排序回调函数对房间进行排序
        """
        if self._sort_callback and len(self._rooms) > 0:
            self._rooms.sort(key=self._sort_callback)

    def push(self, room_id: int) -> None:
        if room_id not in self._rooms and (self.capacity == -1 or len(self._rooms) < self.capacity):
            self._rooms.append(room_id)
            self._sort_rooms()

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
            # 先放到队列开头，然后重新排序以确保正确的优先级
            self._sort_rooms()

    def contains(self, room_id: int) -> bool:
        return room_id in self._rooms

    def all_rooms(self) -> List[int]:
        return list(self._rooms)

    def get_position(self, room_id: int) -> int:
        """
        获取房间在等待队列中的位置（1-based索引）
        如果房间不在队列中，返回-1
        """
        if room_id in self._rooms:
            return self._rooms.index(room_id) + 1
        return -1