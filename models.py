from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from enum import Enum


class ScanStatus(str, Enum):
    """Статус сканирования"""
    SCANNED = "scanned"
    NOT_SCANNED = "not_scanned"
    PARTIAL = "partial"


# Модели для API запросов/ответов
class ScanRequest(BaseModel):
    """Запрос на добавление сканирования"""
    platform: int = Field(..., description="ID платформы")
    product: int = Field(..., description="ID продукта")
    scan_date: datetime = Field(..., description="Дата сканирования")


class ScanResponse(BaseModel):
    """Ответ на добавление сканирования"""
    id: int = Field(..., description="ID записи в БД")
    platform: int
    product: int
    scan_date: date
    scan_time: datetime
    status: str = "success"
    message: str = "Сканирование добавлено"


class ScanRecord(BaseModel):
    """Запись о сканировании"""
    id: int
    platform: int
    product: int
    scan_date: date
    scan_time: datetime
    created_at: datetime


class ProductStatus(BaseModel):
    """Статус продукта"""
    product: int
    last_scan_time: Optional[datetime] = None
    status: ScanStatus = ScanStatus.NOT_SCANNED


class PlatformStatus(BaseModel):
    """Статус платформы"""
    platform: int
    date: date
    scanned_products: List[ProductStatus]
    total_scanned: int
    expected_products: Optional[List[int]] = None  # Ожидаемые продукты для платформы


class ScanStatistics(BaseModel):
    """Статистика сканирований"""
    total_scans: int
    unique_platforms: int
    unique_products: int
    today_scans: int
    last_scan: Optional[Dict[str, Any]] = None


class DateRangeRequest(BaseModel):
    """Запрос для получения данных за период"""
    start_date: date
    end_date: date
    platform: Optional[int] = None


class ScanListResponse(BaseModel):
    """Ответ со списком сканирований"""
    scans: List[ScanRecord]
    total: int
    date: Optional[date] = None
    platform: Optional[int] = None


class PlatformStatusResponse(BaseModel):
    """Ответ со статусом платформы"""
    platform: int
    date: date
    scanned_products: List[Dict[str, Any]]
    total_scanned: int
    missing_products: Optional[List[int]] = None


class AllPlatformsStatusResponse(BaseModel):
    """Ответ со статусом всех платформ"""
    date: date
    platforms: List[PlatformStatusResponse]
    total_platforms: int


# Модели для WebSocket сообщений
class WebSocketScanMessage(BaseModel):
    """WebSocket сообщение о новом сканировании"""
    type: str = "new_scan"
    data: ScanRecord
    statistics: ScanStatistics


class WebSocketStatusMessage(BaseModel):
    """WebSocket сообщение о статусе"""
    type: str = "scan_status_update"
    platform: int
    date: date
    scanned_products: List[Dict[str, Any]]
    total_scanned: int


# Модели для конфигурации платформ и продуктов
class PlatformConfig(BaseModel):
    """Конфигурация платформы"""
    platform_id: int
    platform_name: str
    expected_products: List[int]
    description: Optional[str] = None


class ProductConfig(BaseModel):
    """Конфигурация продукта"""
    product_id: int
    product_name: str
    platform_id: int
    description: Optional[str] = None


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