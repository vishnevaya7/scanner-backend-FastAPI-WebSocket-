import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.models import PairDTO, WSNewPair, WSNewPairData
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
                await manager.broadcast(payload.dict())

                return {"status": "success", "message": "Сканирование добавлено в базу данных"}
            else:
                return {"status": "partial", "message": "Получена только платформа"}
        except Exception as e:
            logger.error(f"Ошибка обработки пары: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/scanners")
    async def get_scanners():
        return {
            "scanners": manager.get_connected_scanners_info(),
            "total_scanners": len(manager.scanner_connections)
        }

    return router
