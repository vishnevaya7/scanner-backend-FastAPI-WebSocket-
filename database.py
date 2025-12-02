
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

