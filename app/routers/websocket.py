import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import EnhancedConnectionManager

logger = logging.getLogger(__name__)


def get_websocket_router(manager: EnhancedConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        logger.info(f"Попытка подключения WebSocket от {client_info}")

        try:
            await manager.connect(websocket)
            logger.info(f"WebSocket успешно подключен от {client_info}")

            while True:
                try:
                    data = await websocket.receive_text()
                    await manager.handle_message(websocket, data)
                except WebSocketDisconnect:
                    logger.info(f"WebSocket отключен клиентом {client_info}")
                    break
                except Exception as e:
                    logger.error(f"Ошибка обработки сообщения от {client_info}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Ошибка WebSocket соединения с {client_info}: {e}")
        finally:
            manager.disconnect(websocket)
            logger.info(f"WebSocket соединение с {client_info} закрыто")

    return router
