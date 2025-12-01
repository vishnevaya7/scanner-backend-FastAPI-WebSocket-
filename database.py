from datetime import datetime, date
from typing import List, Optional, Dict, Any
import aiosqlite
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str = "scanner_data.db"):
        self.db_path = db_path

    async def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS scans
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 platform INTEGER NOT NULL,
                                 product INTEGER NOT NULL,
                                 scan_date DATETIME DEFAULT CURRENT_TIMESTAMP
                             )
                             """)

            # Создаем индексы для быстрого поиска
            await db.execute("""
                             CREATE INDEX IF NOT EXISTS idx_platform_product
                                 ON scans(platform, product)
                             """)

            await db.execute("""
                             CREATE INDEX IF NOT EXISTS idx_scan_date
                                 ON scans(scan_date)
                             """)

            await db.execute("""
                             CREATE INDEX IF NOT EXISTS idx_platform_date
                                 ON scans(platform, scan_date)
                             """)

            await db.commit()
            logger.info("База данных инициализирована")

    async def add_scan(self, platform: int, product: int) -> int:
        """Добавление записи о сканировании"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                                      INSERT INTO scans (platform, product)
                                      VALUES (?, ?)
                                      """, (platform, product))

            await db.commit()
            scan_id = cursor.lastrowid

            logger.info(f"Добавлено сканирование: ID={scan_id}, платформа={platform}, продукт={product}")
            return scan_id

    async def get_scans_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Получение всех сканирований за определенную дату"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                                      SELECT id, platform, product, scan_date
                                      FROM scans
                                      WHERE DATE(scan_date) = ?
                                      ORDER BY scan_date DESC
                                      """, (target_date,))

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_scans_by_date_range(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Получение сканирований за период"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                                      SELECT id, platform, product, scan_date
                                      FROM scans
                                      WHERE DATE(scan_date) BETWEEN ? AND ?
                                      ORDER BY scan_date DESC
                                      """, (start_date, end_date))

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_platform_products_status(self, platform: int, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Получение статуса продуктов для платформы"""
        if target_date is None:
            target_date = date.today()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Получаем все отсканированные продукты для платформы за дату
            cursor = await db.execute("""
                                      SELECT DISTINCT product
                                      FROM scans
                                      WHERE platform = ?
                                        AND DATE(scan_date) = ?
                                      ORDER BY product
                                      """, (platform, target_date))

            scanned_products = await cursor.fetchall()

            return {
                "platform": platform,
                "date": target_date.isoformat(),
                "scanned_products": [
                    {
                        "product": row["product"]
                    } for row in scanned_products
                ],
                "total_scanned": len(scanned_products)
            }

    async def get_all_platforms_status(self, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Получение статуса всех платформ"""
        if target_date is None:
            target_date = date.today()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Получаем все платформы, которые сканировались
            cursor = await db.execute("""
                                      SELECT DISTINCT platform
                                      FROM scans
                                      ORDER BY platform
                                      """)

            platforms = await cursor.fetchall()

            result = []
            for platform_row in platforms:
                platform = platform_row["platform"]
                platform_status = await self.get_platform_products_status(platform, target_date)
                result.append(platform_status)

            return result

    async def check_product_scanned(self, platform: int, product: int, target_date: Optional[date] = None) -> bool:
        """Проверка, был ли продукт отсканирован за дату"""
        if target_date is None:
            target_date = date.today()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                                      SELECT COUNT(*) as count
                                      FROM scans
                                      WHERE platform = ? AND product = ? AND DATE(scan_date) = ?
                                      """, (platform, product, target_date))

            row = await cursor.fetchone()
            return row[0] > 0

    async def get_scan_statistics(self) -> Dict[str, Any]:
        """Получение общей статистики сканирований"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Общее количество сканирований
            cursor = await db.execute("SELECT COUNT(*) as total FROM scans")
            total_scans = (await cursor.fetchone())["total"]

            # Количество уникальных платформ
            cursor = await db.execute("SELECT COUNT(DISTINCT platform) as count FROM scans")
            unique_platforms = (await cursor.fetchone())["count"]

            # Количество уникальных продуктов
            cursor = await db.execute("SELECT COUNT(DISTINCT product) as count FROM scans")
            unique_products = (await cursor.fetchone())["count"]

            # Сканирования за сегодня
            today = date.today()
            cursor = await db.execute("SELECT COUNT(*) as count FROM scans WHERE DATE(scan_date) = ?", (today,))
            today_scans = (await cursor.fetchone())["count"]

            # Последнее сканирование
            cursor = await db.execute("""
                                      SELECT platform, product, scan_date
                                      FROM scans
                                      ORDER BY scan_date DESC LIMIT 1
                                      """)
            last_scan = await cursor.fetchone()

            return {
                "total_scans": total_scans,
                "unique_platforms": unique_platforms,
                "unique_products": unique_products,
                "today_scans": today_scans,
                "last_scan": dict(last_scan) if last_scan else None
            }

    async def delete_scans_by_date(self, target_date: date) -> int:
        """Удаление всех сканирований за определенную дату"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                                      DELETE
                                      FROM scans
                                      WHERE DATE(scan_date) = ?
                                      """, (target_date,))

            await db.commit()
            deleted_count = cursor.rowcount

            logger.info(f"Удалено {deleted_count} записей за дату {target_date}")
            return deleted_count

    async def clear_all_scans(self) -> int:
        """Очистка всех сканирований"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM scans")
            await db.commit()
            deleted_count = cursor.rowcount

            logger.info(f"Удалено всего {deleted_count} записей")
            return deleted_count
