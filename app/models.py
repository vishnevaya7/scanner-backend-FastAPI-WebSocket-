from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# Модели для API запросов/ответов
class ScanRequest(BaseModel):
    """Запрос на добавление сканирования"""
    platform: int = Field(..., description="ID платформы")
    product: int = Field(..., description="ID продукта")
    scan_date: datetime = Field(..., description="Дата сканирования")


# Устаревшая модель для обратной совместимости
class PairDTO(BaseModel):
    """Устаревшая модель пары (для обратной совместимости)"""
    platform: int
    product: Optional[int] = None
    timestamp: Optional[str] = None

    def to_scan_request(self) -> Optional[ScanRequest]:
        """Конвертация в новую модель"""
        if self.product is None:
            return None

        return ScanRequest(
            platform=self.platform,
            product=self.product,
            scan_date=datetime.fromisoformat(self.timestamp)
        )


# WebSocket сообщения
class WSHeartbeatIn(BaseModel):
    type: Literal['heartbeat']
    timestamp: Optional[str] = None
    client: Optional[str] = None


class WSHeartbeatAck(BaseModel):
    type: Literal['heartbeat_ack'] = 'heartbeat_ack'
    timestamp: str


class WSNewPairData(BaseModel):
    platform: int
    product: int
    timestamp: str


class WSNewPair(BaseModel):
    type: Literal['new_pair'] = 'new_pair'
    data: WSNewPairData


class WSScannerInfo(BaseModel):
    client: str
    connected_at: str
    last_heartbeat: str
    is_active: bool


class WSScannerStatus(BaseModel):
    type: Literal['scanner_status'] = 'scanner_status'
    scanners: List[WSScannerInfo]
    has_active_scanners: bool
    timestamp: str
