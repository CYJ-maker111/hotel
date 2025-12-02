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
                    energy_used REAL NOT NULL DEFAULT 0,
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
        self, record_id: int, energy_used: float, cost: float, end_time: Optional[str] = None
    ) -> None:
        """
        更新记录的能耗与费用，可选结束时间。
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            if end_time:
                cur.execute(
                    """
                    UPDATE detail_records
                    SET energy_used = ?, cost = ?, end_time = ?
                    WHERE id = ?
                    """,
                    (energy_used, cost, end_time, record_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE detail_records
                    SET energy_used = ?, cost = ?
                    WHERE id = ?
                    """,
                    (energy_used, cost, record_id),
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

    def get_room_total(self, room_id: int) -> Dict[str, float]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT SUM(energy_used), SUM(cost) FROM detail_records WHERE room_id = ?",
                (room_id,),
            )
            row = cur.fetchone()
            energy = row[0] or 0.0
            cost = row[1] or 0.0
            return {"total_energy": float(energy), "total_cost": float(cost)}
        finally:
            conn.close()

    def get_room_details(self, room_id: int) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, start_time, end_time, mode, target_temp, fan_speed,
                       fee_rate, energy_used, cost, operation_type
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
                        "energy_used": r[7],
                        "cost": r[8],
                        "operation_type": r[9],
                    }
                )
            return result
        finally:
            conn.close()

    def get_summary(self) -> Dict[str, float]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT SUM(energy_used), SUM(cost) FROM detail_records")
            row = cur.fetchone()
            energy = row[0] or 0.0
            cost = row[1] or 0.0
            return {"total_energy": float(energy), "total_cost": float(cost)}
        finally:
            conn.close()


