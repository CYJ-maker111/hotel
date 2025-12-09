import sqlite3
import os

# 数据库路径
db_path = os.path.join(os.path.dirname(__file__), 'hotel_ac.db')

def init_database():
    """初始化数据库，创建必要的表并迁移字段"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 创建入住记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkin_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                guest_name TEXT NOT NULL,
                checkin_time TEXT NOT NULL,
                checkout_time TEXT,
                status TEXT NOT NULL DEFAULT 'CHECKED_IN',
                power_off_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # 检查checkin_records是否需要添加power_off_count字段
        cursor.execute("PRAGMA table_info(checkin_records)")
        checkin_columns = [column[1] for column in cursor.fetchall()]
        
        if 'power_off_count' not in checkin_columns:
            cursor.execute("ALTER TABLE checkin_records ADD COLUMN power_off_count INTEGER NOT NULL DEFAULT 0")
            print("✓ 已添加 checkin_records.power_off_count 字段")
        
        # 检查detail_records表是否需要添加新字段
        cursor.execute("PRAGMA table_info(detail_records)")
        detail_columns = [column[1] for column in cursor.fetchall()]
        
        # 添加request_time字段
        if 'request_time' not in detail_columns:
            cursor.execute("ALTER TABLE detail_records ADD COLUMN request_time TEXT")
            # 将现有记录的request_time设置为start_time
            cursor.execute("UPDATE detail_records SET request_time = start_time WHERE request_time IS NULL")
            print("✓ 已添加 detail_records.request_time 字段")
        
        # 添加service_duration字段
        if 'service_duration' not in detail_columns:
            cursor.execute("ALTER TABLE detail_records ADD COLUMN service_duration INTEGER DEFAULT 0")
            # 计算现有记录的服务时长
            cursor.execute("""
                UPDATE detail_records 
                SET service_duration = CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER)
                WHERE end_time IS NOT NULL AND service_duration = 0
            """)
            print("✓ 已添加 detail_records.service_duration 字段")
        
        # 添加accumulated_cost字段
        if 'accumulated_cost' not in detail_columns:
            cursor.execute("ALTER TABLE detail_records ADD COLUMN accumulated_cost REAL DEFAULT 0")
            # 计算现有记录的累积费用
            cursor.execute("""
                UPDATE detail_records 
                SET accumulated_cost = (
                    SELECT SUM(d2.cost) 
                    FROM detail_records d2 
                    WHERE d2.room_id = detail_records.room_id 
                    AND d2.id <= detail_records.id
                )
            """)
            print("✓ 已添加 detail_records.accumulated_cost 字段")
        
        conn.commit()
        print("\n✓ 数据库迁移完成！")
    except Exception as e:
        print(f"✗ 数据库初始化失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()

