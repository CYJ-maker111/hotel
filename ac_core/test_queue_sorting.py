import unittest
from .queues import ServedQueue

class TestQueueSorting(unittest.TestCase):
    def setUp(self):
        # 初始化服务队列
        self.served_queue = ServedQueue(capacity=10)
        
        # 模拟房间数据：风速和服务时长
        # 高风速=3, 中风速=2, 低风速=1
        self.rooms_fan_speed = {1: 3, 2: 2, 3: 2}
        # 服务时长：room2(120秒) > room3(60秒)
        self.service_times = {1: 0, 2: 120, 3: 60}
        
        # 设置排序回调函数，模拟scheduler中的实现
        self.served_queue.set_sort_callback(lambda rid: (
            -self.rooms_fan_speed.get(rid, 0),  # 风速降序
            -self.service_times.get(rid, 0)     # 服务时长降序
        ))

    def test_queue_sorting(self):
        # 按[room3, room2, room1]的顺序加入队列
        self.served_queue.push(3)
        self.served_queue.push(2)
        self.served_queue.push(1)
        
        # 获取排序后的队列
        sorted_rooms = self.served_queue.all_rooms()
        
        # 预期顺序：room1(高风速) > room2(中风速/时间长) > room3(中风速/时间短)
        self.assertEqual(sorted_rooms, [1, 2, 3], 
                         f"排序错误: 预期[1,2,3], 实际{sorted_rooms}")

if __name__ == '__main__':
    unittest.main()