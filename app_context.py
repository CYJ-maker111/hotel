from ac_core import HotelACSystem

# 简单全局单例系统：5 间房，最多同时服务 3 间房，等待队列大小为 2，时间片 30 秒
system = HotelACSystem(room_count=5, served_capacity=3, waiting_capacity=2, time_slice_seconds=30)
