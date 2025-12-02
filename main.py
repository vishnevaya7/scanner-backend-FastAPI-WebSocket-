from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import asyncio
from datetime import datetime, date
import logging
from contextlib import asynccontextmanager
from colorlog import ColoredFormatter
import colorama

from database import DatabaseManager
from models import (
    ScanRequest, ScanResponse, ScanRecord, PlatformStatus, ScanStatistics,
    DateRangeRequest, ScanListResponse, PlatformStatusResponse, 
    AllPlatformsStatusResponse, PairDTO
)

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


@app.get("/api/pairs")
async def get_all_pairs():
    """Получение всех сканирований за сегодня (обратная совместимость)"""
    try:
        # Получаем сканирования за сегодня
        today_scans = await db_manager.get_scans_by_date(date.today())
        
        # Конвертируем в формат PairDTO для обратной совместимости
        pairs = []
        for scan in today_scans:
            pairs.append({
                "platform": scan["platform"],
                "product": scan["product"],
                "timestamp": scan["scan_date"]
            })
        
        return {
            "pairs": pairs,
            "total": len(pairs)
        }
    except Exception as e:
        logger.error(f"Ошибка получения пар: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/pairs")
async def clear_pairs():
    """Очистка всех сканирований (обратная совместимость)"""
    try:
        # Очищаем все сканирования в базе данных
        deleted_count = await db_manager.clear_all_scans()

        # Уведомляем клиентов об очистке
        message = {
            "type": "pairs_cleared",
            "data": {},
            "total_pairs": 0,
            "deleted_count": deleted_count
        }
        await manager.broadcast(message)

        return {"status": "success", "message": f"Очищено {deleted_count} сканирований"}
    except Exception as e:
        logger.error(f"Ошибка очистки: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def get_status():
    """Расширенный статус сервера"""
    try:
        # Получаем статистику из базы данных
        statistics = await db_manager.get_scan_statistics()
        today_scans = await db_manager.get_scans_by_date(date.today())
        
        return {
            "status": "running",
            "total_scans": statistics["total_scans"],
            "today_scans": len(today_scans),
            "active_connections": len(manager.active_connections),
            "connected_scanners": len(manager.scanner_connections),
            "scanners_info": manager.get_connected_scanners_info(),
            "statistics": statistics,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scanners")
async def get_scanners():
    """Получение информации о подключенных сканерах"""
    return {
        "scanners": manager.get_connected_scanners_info(),
        "total_scanners": len(manager.scanner_connections)
    }


# Новые API endpoints для работы с базой данных
@app.post("/api/scans", response_model=ScanResponse)
async def add_scan(scan_request: ScanRequest):
    """Добавление нового сканирования"""
    try:
        scan_id = await db_manager.add_scan(
            platform=scan_request.platform,
            product=scan_request.product
        )
        
        scan_datetime = scan_request.scan_datetime or datetime.now()
        
        # Получаем статистику
        statistics = await db_manager.get_scan_statistics()
        
        # Отправляем уведомление через WebSocket в формате, совместимом с frontend
        message = {
            "type": "new_pair",
            "data": {
                "platform": scan_request.platform,
                "product": scan_request.product,
                "timestamp": scan_datetime.isoformat()
            },
            "total_pairs": statistics["total_scans"],
            "statistics": statistics
        }
        await manager.broadcast(message)
        
        return ScanResponse(
            id=scan_id,
            platform=scan_request.platform,
            product=scan_request.product,
            scan_date=scan_datetime.date(),
            scan_time=scan_datetime
        )
        
    except Exception as e:
        logger.error(f"Ошибка добавления сканирования: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scans/today")
async def get_today_scans():
    """Получение сканирований за сегодня"""
    try:
        today = date.today()
        scans = await db_manager.get_scans_by_date(today)
        return {
            "scans": scans,
            "total": len(scans),
            "date": today.isoformat()
        }
    except Exception as e:
        logger.error(f"Ошибка получения сканирований: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scans/date/{target_date}")
async def get_scans_by_date(target_date: date):
    """Получение сканирований за определенную дату"""
    try:
        scans = await db_manager.get_scans_by_date(target_date)
        return {
            "scans": scans,
            "total": len(scans),
            "date": target_date.isoformat()
        }
    except Exception as e:
        logger.error(f"Ошибка получения сканирований: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scans/date-range")
async def get_scans_by_date_range(date_range: DateRangeRequest):
    """Получение сканирований за период"""
    try:
        scans = await db_manager.get_scans_by_date_range(date_range.start_date, date_range.end_date)
        return {
            "scans": scans,
            "total": len(scans),
            "start_date": date_range.start_date.isoformat(),
            "end_date": date_range.end_date.isoformat(),
            "platform": date_range.platform
        }
    except Exception as e:
        logger.error(f"Ошибка получения сканирований: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/platforms/{platform_id}/status")
async def get_platform_status(platform_id: int, target_date: Optional[date] = None):
    """Получение статуса платформы"""
    try:
        if target_date is None:
            target_date = date.today()
            
        status = await db_manager.get_platform_products_status(platform_id, target_date)
        return status
    except Exception as e:
        logger.error(f"Ошибка получения статуса платформы: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/platforms/status")
async def get_all_platforms_status(target_date: Optional[date] = None):
    """Получение статуса всех платформ"""
    try:
        if target_date is None:
            target_date = date.today()
            
        platforms_status = await db_manager.get_all_platforms_status(target_date)
        return {
            "date": target_date.isoformat(),
            "platforms": platforms_status,
            "total_platforms": len(platforms_status)
        }
    except Exception as e:
        logger.error(f"Ошибка получения статуса платформ: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/statistics")
async def get_statistics():
    """Получение общей статистики"""
    try:
        statistics = await db_manager.get_scan_statistics()
        return statistics
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products/{platform_id}/{product_id}/check")
async def check_product_scanned(platform_id: int, product_id: int, target_date: Optional[date] = None):
    """Проверка, был ли продукт отсканирован"""
    try:
        if target_date is None:
            target_date = date.today()
            
        is_scanned = await db_manager.check_product_scanned(platform_id, product_id, target_date)
        return {
            "platform": platform_id,
            "product": product_id,
            "date": target_date.isoformat(),
            "is_scanned": is_scanned,
            "status": "scanned" if is_scanned else "not_scanned"
        }
    except Exception as e:
        logger.error(f"Ошибка проверки продукта: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Enhanced Scanner Backend API with SQLite Database",
        "version": "2.0.0",
        "features": [
            "SQLite database for persistent storage",
            "Scanner heartbeat monitoring",
            "Real-time scanner status tracking",
            "Enhanced WebSocket management",
            "Date-based filtering and statistics",
            "Platform and product status tracking"
        ],
        "endpoints": {
            "websocket": "/ws",
            "legacy": {
                "post_data": "/api/sp_data",
                "get_pairs": "/api/pairs",
                "clear_pairs": "/api/pairs (DELETE)"
            },
            "scans": {
                "add_scan": "/api/scans (POST)",
                "get_today": "/api/scans/today",
                "get_by_date": "/api/scans/date/{date}",
                "get_by_range": "/api/scans/date-range (POST)",
                "delete_by_date": "/api/scans/date/{date} (DELETE)",
                "clear_all": "/api/scans (DELETE)"
            },
            "platforms": {
                "platform_status": "/api/platforms/{platform_id}/status",
                "all_platforms_status": "/api/platforms/status"
            },
            "products": {
                "check_scanned": "/api/products/{platform_id}/{product_id}/check"
            },
            "system": {
                "status": "/api/status",
                "statistics": "/api/statistics",
                "scanners": "/api/scanners"
            }
        },
        "database": {
            "type": "SQLite",
            "features": [
                "Постоянное хранение данных",
                "Индексы для быстрого поиска",
                "Фильтрация по датам",
                "Статистика сканирований"
            ]
        }
    }

