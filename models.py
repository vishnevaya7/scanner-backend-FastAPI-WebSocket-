from pydantic import BaseModel, Field
from typing import Optional
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