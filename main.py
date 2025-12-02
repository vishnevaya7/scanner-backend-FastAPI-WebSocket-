from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json
import asyncio
from datetime import datetime, date
import logging
from contextlib import asynccontextmanager
from colorlog import ColoredFormatter
import colorama

from database import DatabaseManager
from models import PairDTO

def configure_logging():
    colorama.just_fix_windows_console()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # remove existing handlers to prevent duplicate logs on reload
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s | %(asctime)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Apply same handler to uvicorn loggers
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        l = logging.getLogger(name)
        l.setLevel(logging.INFO)
        for h in list(l.handlers):
            l.removeHandler(h)
        l.addHandler(handler)
        l.propagate = False

configure_logging()
logger = logging.getLogger(__name__)

# Инициализация базы данных
db_manager = DatabaseManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    try:
        await db_manager.init_database()
        logger.info("Приложение инициализировано")
        yield
    finally:
        # Shutdown
        logger.info("Завершение работы приложения...")
        # Закрываем все WebSocket соединения корректно
        if 'manager' in globals():
            await manager.close_all_connections()
        logger.info("Приложение завершено")

app = FastAPI(
    title="Enhanced Scanner Backend", 
    version="1.1.0",
    lifespan=lifespan
)

# CORS настройки - расширенные для WebSocket
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)


class WebSocketMessage(BaseModel):
    type: str
    data: dict
    total_pairs: int


class HeartbeatMessage(BaseModel):
    type: str
    timestamp: str
    client: str


# Убрано локальное хранение - все данные теперь в базе данных


# Улучшенный WebSocket менеджер без локального хранения
class EnhancedConnectionManager:
    def __init__(self, database_manager: DatabaseManager):
        self.active_connections: List[WebSocket] = []
        self.scanner_connections: dict = {}  # WebSocket -> scanner_info
        self.db_manager = database_manager

    async def connect(self, websocket: WebSocket):
        try:
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info(f"WebSocket подключен. Всего подключений: {len(self.active_connections)}")

            # Отправляем начальные данные
            await self.send_initial_data(websocket)
        except Exception as e:
            logger.error(f"Ошибка при подключении WebSocket: {e}")
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            raise

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Удаляем информацию о сканере если есть
        if websocket in self.scanner_connections:
            scanner_info = self.scanner_connections.pop(websocket)
            logger.info(f"Сканер отключен: {scanner_info.get('client', 'unknown')}")
            # Уведомляем всех клиентов об отключении сканера
            try:
                asyncio.create_task(self.broadcast_scanner_status())
            except Exception as e:
                logger.error(f"Ошибка уведомления о статусе сканера: {e}")

        logger.info(f"WebSocket отключен. Всего подключений: {len(self.active_connections)}")

    async def close_all_connections(self):
        """Корректное закрытие всех WebSocket соединений"""
        logger.info("Закрытие всех WebSocket соединений...")
        for connection in self.active_connections.copy():
            try:
                await connection.close(code=1000, reason="Server shutdown")
            except Exception as e:
                logger.error(f"Ошибка закрытия WebSocket: {e}")
        
        self.active_connections.clear()
        self.scanner_connections.clear()
        logger.info("Все WebSocket соединения закрыты")

    async def send_initial_data(self, websocket: WebSocket):
        try:
            # Получаем данные за сегодня из базы данных
            today_scans = await self.db_manager.get_scans_by_date(date.today())
            statistics = await self.db_manager.get_scan_statistics()
            
            # Конвертируем сканирования в формат пар для совместимости с frontend
            pairs_data = []
            for scan in today_scans:
                pairs_data.append({
                    "platform": scan["platform"],
                    "product": scan["product"],
                    "timestamp": scan["scan_date"]
                })
            
            message = {
                "type": "initial_data",
                "data": pairs_data,
                "total_pairs": len(pairs_data),
                "statistics": statistics
            }
            
            logger.info(f"Отправка начальных данных: {len(pairs_data)} пар")
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
            
        except Exception as e:
            logger.error(f"Ошибка отправки начальных данных: {e}")
            raise

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

            # Удаляем отключенные соединения
            for connection in disconnected:
                self.disconnect(connection)

    def register_scanner(self, websocket: WebSocket, scanner_info: dict):
        """Регистрация сканера"""
        self.scanner_connections[websocket] = {
            'client': scanner_info.get('client', 'unknown'),
            'last_heartbeat': datetime.now(),
            'connected_at': datetime.now()
        }
        logger.info(f"Сканер зарегистрирован: {scanner_info.get('client', 'unknown')}")

        # Уведомляем всех клиентов о подключении сканера
        asyncio.create_task(self.broadcast_scanner_status())

    async def broadcast_scanner_status(self):
        """Отправка статуса сканеров всем подключенным клиентам"""
        scanners_info = self.get_connected_scanners_info()
        message = {
            "type": "scanner_status",
            "scanners": scanners_info,
            "has_active_scanners": len([s for s in scanners_info if s['is_active']]) > 0,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)

    def update_scanner_heartbeat(self, websocket: WebSocket):
        """Обновление времени последнего heartbeat"""
        if websocket in self.scanner_connections:
            self.scanner_connections[websocket]['last_heartbeat'] = datetime.now()

    def get_connected_scanners_info(self):
        """Получение информации о подключенных сканерах"""
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
        """Обработка входящих сообщений"""
        try:
            data = json.loads(message)
            message_type = data.get('type', 'unknown')

            if message_type == 'heartbeat':
                # Обработка heartbeat сообщения
                if websocket not in self.scanner_connections:
                    # Первый heartbeat - регистрируем сканер
                    self.register_scanner(websocket, data)
                else:
                    # Обновляем время последнего heartbeat
                    self.update_scanner_heartbeat(websocket)

                logger.info(f"Heartbeat от {data.get('client', 'unknown')}")

                # Отправляем подтверждение
                response = {
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send_text(json.dumps(response))

            else:
                logger.info(f"Получено сообщение типа {message_type} от клиента")

        except json.JSONDecodeError:
            logger.error(f"Ошибка парсинга JSON: {message}")
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")


manager = EnhancedConnectionManager(db_manager)



# WebSocket endpoint с улучшенной обработкой
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    logger.info(f"Попытка подключения WebSocket от {client_info}")
    
    try:
        await manager.connect(websocket)
        logger.info(f"WebSocket успешно подключен от {client_info}")
        
        while True:
            try:
                # Ждем сообщения от клиента
                data = await websocket.receive_text()
                await manager.handle_message(websocket, data)
            except WebSocketDisconnect:
                logger.info(f"WebSocket отключен клиентом {client_info}")
                break
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения от {client_info}: {e}")
                # Продолжаем работу, не разрывая соединение
                continue
                
    except Exception as e:
        logger.error(f"Ошибка WebSocket соединения с {client_info}: {e}")
    finally:
        manager.disconnect(websocket)
        logger.info(f"WebSocket соединение с {client_info} закрыто")


# REST API endpoints
@app.post("/api/sp_data")
async def post_data(pair: PairDTO):
    """Прием пары от десктопного приложения (обратная совместимость)"""
    try:
        # Добавляем timestamp если не указан
        if not pair.timestamp:
            pair.timestamp = datetime.now().isoformat()

        logger.info(f"Получена пара: платформа {pair.platform}, продукт {pair.product}")

        # Если есть продукт, сохраняем в базу данных
        if pair.product is not None:
            # Сохраняем в базу данных
            scan_id = await db_manager.add_scan(
                platform=pair.platform,
                product=pair.product
            )


            # Отправляем уведомление через WebSocket в формате, совместимом с frontend
            message = {
                "type": "new_pair",
                "data": {
                    "platform": pair.platform,
                    "product": pair.product,
                    "timestamp": pair.timestamp
                }
            }
            await manager.broadcast(message)

            return {"status": "success", "message": "Сканирование добавлено в базу данных"}
        else:
            return {"status": "partial", "message": "Получена только платформа"}

    except Exception as e:
        logger.error(f"Ошибка обработки пары: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/scanners")
async def get_scanners():
    """Получение информации о подключенных сканерах"""
    return {
        "scanners": manager.get_connected_scanners_info(),
        "total_scanners": len(manager.scanner_connections)
    }

