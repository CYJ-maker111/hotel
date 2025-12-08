from typing import Dict


class ServiceTimer:
    """
    服务计时器：统计每个房间的送风时长（秒）
    """

    def __init__(self):
        self._served_seconds: Dict[int, int] = {}

    def reset_timer(self, room_id: int) -> None:
        self._served_seconds[room_id] = 0

    def tick(self, delta_seconds: int) -> None:
        for room_id in list(self._served_seconds.keys()):
            self._served_seconds[room_id] += delta_seconds

    def get_service_time(self, room_id: int) -> int:
        return self._served_seconds.get(room_id, 0)
        
    def remove_timer(self, room_id: int) -> None:
        """
        从服务计时器中移除房间ID，当房间离开服务队列时调用
        """
        if room_id in self._served_seconds:
            del self._served_seconds[room_id]


class WaitTimer:
    """
    等待计时器：统计每个房间的等待时长（秒）
    """

    def __init__(self):
        self._waiting_seconds: Dict[int, int] = {}

    def create_timer(self, room_id: int) -> None:
        self._waiting_seconds[room_id] = 0

    def reset_timer(self, room_id: int) -> None:
        self._waiting_seconds[room_id] = 0

    def tick(self, delta_seconds: int) -> None:
        for room_id in list(self._waiting_seconds.keys()):
            self._waiting_seconds[room_id] += delta_seconds

    def get_wait_time(self, room_id: int) -> int:
        return self._waiting_seconds.get(room_id, 0)


