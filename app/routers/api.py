import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.models import PairDTO, WSNewPair, WSNewPairData, WSChangePlatformData, WSChangePlatform
from app.services.websocket_manager import EnhancedConnectionManager
from app.database import DatabaseManager

logger = logging.getLogger(__name__)


def get_api_router(manager: EnhancedConnectionManager, db_manager: DatabaseManager) -> APIRouter:
    router = APIRouter()

    @router.post("/api/scan_data")
    async def post_data(pair: PairDTO):
        try:
            if not pair.timestamp:
                pair.timestamp = datetime.now().isoformat()

            logger.info(f"Получена пара: платформа {pair.platform}, продукт {pair.product}")
            if pair.platform is None:
                return {"status": "error", "message": "Не указана платформа"}

            if pair.product is not None:
                await db_manager.add_scan(
                    platform=pair.platform,
                    product=pair.product
                )

                payload = WSNewPair(
                    data=WSNewPairData(
                        platform=pair.platform,
                        product=pair.product,
                        timestamp=pair.timestamp
                    )
                )
                await manager.broadcast(payload.model_dump())

                return {"status": "success", "message": "Сканирование добавлено в базу данных"}
            else:
                await manager.broadcast(WSChangePlatform(
                    data=WSChangePlatformData(
                        platform=pair.platform
                    )
                ).model_dump())
                return {"status": "success", "message": "Платформа изменена"}
        except Exception as e:
            logger.error(f"Ошибка обработки пары: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/scan/pairs")
    async def get_scan_pairs(
        platform: int | None = None,
        product: int | None = None,
        dateFrom: str | None = None,
        dateTo: str | None = None,
        date: str | None = None,
    ):
        try:
            logger.info(
                f"Запрос пар: platform={platform}, product={product}, date={date}, dateFrom={dateFrom}, dateTo={dateTo}"
            )
            pairs = await db_manager.get_scan_pairs(
                platform=platform,
                product=product,
                date_from=dateFrom,
                date_to=dateTo,
                date=date,
            )
            platform_map: dict[int, list[int]] = {}
            for item in pairs:
                plat = item["platform"]
                prod = item["product"]
                if plat not in platform_map:
                    platform_map[plat] = []
                platform_map[plat].append(prod)
            return platform_map
        except Exception as e:
            logger.error(f"Ошибка получения пар: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/scanners")
    async def get_scanners():
        return {
            "scanners": manager.get_connected_scanners_info(),
            "total_scanners": len(manager.scanner_connections)
        }

    return router
