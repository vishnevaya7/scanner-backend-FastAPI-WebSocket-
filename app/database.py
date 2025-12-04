import os
import aiosqlite
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str = "data/scanner_data.db"):
        self.db_path = db_path
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @asynccontextmanager
    async def _connect(self) -> aiosqlite.Connection:
        """Создает подключение и применяет оптимизационные PRAGMA для SQLite."""
        db = await aiosqlite.connect(self.db_path)
        # Оптимизация WAL и режимов синхронизации/кэша для повышения пропускной способности
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA temp_store=MEMORY;")
        await db.execute("PRAGMA cache_size=-20000;")  # ~20 MB page cache
        try:
            yield db
        finally:
            await db.close()

    async def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        async with self._connect() as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS scans
                (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform INTEGER NOT NULL,
                    product INTEGER NOT NULL,
                    scan_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Индексы для быстрого поиска
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_platform_product
                    ON scans(platform, product)
                """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scan_date
                    ON scans(scan_date)
                """
            )

            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_platform_date
                    ON scans(platform, scan_date)
                """
            )

            await db.commit()
            logger.info("База данных инициализирована")

    async def add_scan(self, platform: int, product: int) -> int:
        """Добавление записи о сканировании"""
        async with self._connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO scans (platform, product)
                VALUES (?, ?)
                """,
                (platform, product),
            )

            await db.commit()
            scan_id = cursor.lastrowid

            logger.info(
                f"Добавлено сканирование: ID={scan_id}, платформа={platform}, продукт={product}"
            )
            return scan_id

    async def get_scan_pairs(
        self,
        platform: int | None = None,
        product: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        date: str | None = None,
    ) -> list[dict]:
        """Получение списка сканирований (пар) с фильтрами.

        Параметры даты ожидаются в ISO-формате. Если указан параметр `date`,
        он интерпретируется как один день (date 00:00:00 .. 23:59:59.999999).
        """
        where_clauses = []
        params: list = []

        if platform is not None:
            where_clauses.append("platform = ?")
            params.append(platform)

        if product is not None:
            where_clauses.append("product = ?")
            params.append(product)

        # Обработка даты: либо одиночный день, либо диапазон
        if date:
            # Используем BETWEEN по строковым значениям ISO
            where_clauses.append("scan_date BETWEEN ? AND ?")
            # В БД CURRENT_TIMESTAMP хранится как 'YYYY-MM-DD HH:MM:SS', поэтому используем пробел, а не 'T'
            normalized_date = date.replace("T", " ")
            start = f"{normalized_date} 00:00:00"
            end = f"{normalized_date} 23:59:59.999999"
            params.extend([start, end])
        else:
            if date_from:
                where_clauses.append("scan_date >= ?")
                # Если пришла только дата без времени
                df = date_from.replace("T", " ")
                params.append(df if " " in df and ":" in df else f"{df} 00:00:00")
            if date_to:
                where_clauses.append("scan_date <= ?")
                dt = date_to.replace("T", " ")
                params.append(dt if " " in dt and ":" in dt else f"{dt} 23:59:59.999999")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT id, platform, product, scan_date
            FROM scans
            {where_sql}
            ORDER BY scan_date DESC
        """

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                result = [
                    {
                        "id": row["id"],
                        "platform": row["platform"],
                        "product": row["product"],
                        "timestamp": row["scan_date"],
                    }
                    for row in rows
                ]

        logger.info(
            f"Найдено пар: {len(result)} (filters: platform={platform}, product={product}, date={date}, date_from={date_from}, date_to={date_to})"
        )
        return result
