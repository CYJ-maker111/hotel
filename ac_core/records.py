import sqlite3
from typing import Optional, List, Dict, Any


class DetailRecord:
    """
    详单对象：负责操作记录与费用计算，并持久化到 SQLite 数据库。
    """

    def __init__(self, db_path: str = "hotel_ac.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS detail_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    mode TEXT NOT NULL,
                    target_temp REAL NOT NULL,
                    fan_speed TEXT NOT NULL,
                    fee_rate REAL NOT NULL,
                    cost REAL NOT NULL DEFAULT 0,
                    operation_type TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_record(
        self,
        room_id: int,
        start_time: str,
        mode: str,
        target_temp: float,
        fan_speed: str,
        fee_rate: float,
        operation_type: str,
    ) -> int:
        """
        创建一条新的详单记录，返回记录 ID。
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO detail_records
                (room_id, start_time, mode, target_temp, fan_speed,
                 fee_rate, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (room_id, start_time, mode, target_temp, fan_speed, fee_rate, operation_type),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update_on_service(
        self, record_id: int, cost: float, end_time: Optional[str] = None
    ) -> None:
        """
        更新记录的费用，可选结束时间。
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            if end_time:
                cur.execute(
                    """
                    UPDATE detail_records
                    SET cost = ?, end_time = ?
                    WHERE id = ?
                    """,
                    (cost, end_time, record_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE detail_records
                    SET cost = ?
                    WHERE id = ?
                    """,
                    (cost, record_id),
                )
            conn.commit()
        finally:
            conn.close()

    def update_fee_rate(self, record_id: int, fee_rate: float, fan_speed: str) -> None:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE detail_records
                SET fee_rate = ?, fan_speed = ?
                WHERE id = ?
                """,
                (fee_rate, fan_speed, record_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_record(self, record_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, room_id, start_time, end_time, mode, target_temp, fan_speed,
                       fee_rate, cost, operation_type
                FROM detail_records
                WHERE id = ?
                """,
                (record_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "room_id": row[1],
                    "start_time": row[2],
                    "end_time": row[3],
                    "mode": row[4],
                    "target_temp": row[5],
                    "fan_speed": row[6],
                    "fee_rate": row[7],
                    "cost": row[8],
                    "operation_type": row[9],
                }
            return None
        finally:
            conn.close()

    def get_room_total(self, room_id: int) -> Dict[str, float]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT SUM(cost) FROM detail_records WHERE room_id = ?",
                (room_id,),
            )
            row = cur.fetchone()
            cost = row[0] or 0.0
            return {"total_cost": round(float(cost), 2)}
        finally:
            conn.close()

    def get_room_details(self, room_id: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, start_time, end_time, mode, target_temp, fan_speed,
                       fee_rate, cost, operation_type
                FROM detail_records
                WHERE room_id = ?
                ORDER BY id ASC
                """,
                (room_id,),
            )
            rows = cur.fetchall()
            result: List[Dict[str, Any]] = []
            for r in rows:
                result.append(
                    {
                        "id": r[0],
                        "start_time": r[1],
                        "end_time": r[2],
                        "mode": r[3],
                        "target_temp": r[4],
                        "fan_speed": r[5],
                        "fee_rate": r[6],
                        "cost": r[7],
                        "operation_type": r[8],
                    }
                )
            return result
        finally:
            conn.close()

    def get_summary(self) -> Dict[str, float]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT SUM(cost) FROM detail_records")
            row = cur.fetchone()
            cost = row[0] or 0.0
            return {"total_cost": float(cost)}
        finally:
            conn.close()

    def get_summary_range(
        self, start_time: Optional[str] = None, end_time: Optional[str] = None
    ) -> Dict[str, float]:
        """
        按时间范围统计总费用。

        说明：
        - start_time / end_time 均为字符串，格式建议为 "YYYY-MM-DD HH:MM:SS"
        - 若只提供 start_time，则统计 start_time 之后的所有记录
        - 若只提供 end_time，则统计 end_time 之前的所有记录
        - 若两者都为空，则等同于 get_summary
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            sql = "SELECT SUM(cost) FROM detail_records WHERE 1=1"
            params: list = []

            if start_time:
                sql += " AND start_time >= ?"
                params.append(start_time)
            if end_time:
                sql += " AND start_time <= ?"
                params.append(end_time)

            cur.execute(sql, params)
            row = cur.fetchone()
            cost = row[0] or 0.0
            return {"total_cost": float(cost)}
        finally:
            conn.close()
    
    def clear_all_records(self) -> None:
        """
        清除详单表中的所有记录。
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM detail_records")
            conn.commit()
        finally:
            conn.close()


