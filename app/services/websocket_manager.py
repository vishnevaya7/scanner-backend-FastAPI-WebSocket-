import json
import asyncio
import logging
from datetime import datetime
from typing import List
from fastapi import WebSocket

from app.repository.database import DatabaseManager
from app.models import WSHeartbeatAck, WSScannerStatus, WSScannerInfo


logger = logging.getLogger(__name__)


class EnhancedConnectionManager:
    def __init__(self, database_manager: DatabaseManager):
        self.active_connections: List[WebSocket] = []
        self.scanner_connections: dict = {}
        self.db_manager = database_manager

    async def connect(self, websocket: WebSocket):
        try:
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info(f"WebSocket подключен. Всего подключений: {len(self.active_connections)}")
        except Exception as e:
            logger.error(f"Ошибка при подключении WebSocket: {e}")
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            raise

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        if websocket in self.scanner_connections:
            scanner_info = self.scanner_connections.pop(websocket)
            logger.info(f"Сканер отключен: {scanner_info.get('client', 'unknown')}")
            try:
                asyncio.create_task(self.broadcast_scanner_status())
            except Exception as e:
                logger.error(f"Ошибка уведомления о статусе сканера: {e}")

        logger.info(f"WebSocket отключен. Всего подключений: {len(self.active_connections)}")

    async def close_all_connections(self):
        logger.info("Закрытие всех WebSocket соединений...")
        for connection in self.active_connections.copy():
            try:
                await connection.close(code=1000, reason="Server shutdown")
            except Exception as e:
                logger.error(f"Ошибка закрытия WebSocket: {e}")
        self.active_connections.clear()
        self.scanner_connections.clear()
        logger.info("Все WebSocket соединения закрыты")

    async def broadcast(self, message: dict):
        if self.active_connections:
            message_text = json.dumps(message, ensure_ascii=False)
            disconnected = []

            for connection in self.active_connections:
                try:
                    await connection.send_text(message_text)
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения: {e}")
                    disconnected.append(connection)

            for connection in disconnected:
                self.disconnect(connection)

    def register_scanner(self, websocket: WebSocket, scanner_info: dict):
        self.scanner_connections[websocket] = {
            'client': scanner_info.get('client', 'unknown'),
            'last_heartbeat': datetime.now(),
            'connected_at': datetime.now()
        }
        logger.info(f"Сканер зарегистрирован: {scanner_info.get('client', 'unknown')}")
        asyncio.create_task(self.broadcast_scanner_status())

    async def broadcast_scanner_status(self):
        scanners_info = self.get_connected_scanners_info()
        payload = WSScannerStatus(
            scanners=[
                WSScannerInfo(**s) for s in scanners_info
            ],
            has_active_scanners=len([s for s in scanners_info if s['is_active']]) > 0,
            timestamp=datetime.now().isoformat()
        )
        await self.broadcast(payload.dict())

    def update_scanner_heartbeat(self, websocket: WebSocket):
        if websocket in self.scanner_connections:
            self.scanner_connections[websocket]['last_heartbeat'] = datetime.now()

    def get_connected_scanners_info(self):
        scanners = []
        for websocket, info in self.scanner_connections.items():
            scanners.append({
                'client': info['client'],
                'connected_at': info['connected_at'].isoformat(),
                'last_heartbeat': info['last_heartbeat'].isoformat(),
                'is_active': (datetime.now() - info['last_heartbeat']).seconds < 60
            })
        return scanners

    async def handle_message(self, websocket: WebSocket, message: str):
        try:
            data = json.loads(message)
            message_type = data.get('type', 'unknown')

            if message_type == 'heartbeat':
                if websocket not in self.scanner_connections:
                    self.register_scanner(websocket, data)
                else:
                    self.update_scanner_heartbeat(websocket)

                logger.info(f"Heartbeat от {data.get('client', 'unknown')}")

                response = WSHeartbeatAck(timestamp=datetime.now().isoformat())
                await websocket.send_text(json.dumps(response.dict()))
            else:
                logger.info(f"Получено сообщение типа {message_type} от клиента")
        except json.JSONDecodeError:
            logger.error(f"Ошибка парсинга JSON: {message}")
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
