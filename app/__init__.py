import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging_config import configure_logging
from dotenv import load_dotenv
from app.repository.database import DatabaseManager
from app.repository.legacy_database import LegacyDatabaseManager
from app.services.websocket_manager import EnhancedConnectionManager
from app.routers.websocket import get_websocket_router
from app.routers.api import get_api_router
from app.routers import auth as auth_router


def create_app() -> FastAPI:
    load_dotenv()
    configure_logging()
    logger = logging.getLogger(__name__)

    db_manager = DatabaseManager()
    legacy_db_manager = LegacyDatabaseManager()
    manager = EnhancedConnectionManager(db_manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await db_manager.init_database()
            logger.info("Приложение инициализировано")
            yield
        finally:
            logger.info("Завершение работы приложения...")
            await manager.close_all_connections()
            logger.info("Приложение завершено")

    app = FastAPI(
        title="Enhanced Scanner Backend",
        version="1.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Публичный роутер логина (без зависимости авторизации)
    app.include_router(auth_router.router)

    # Защищенные API-роуты
    app.include_router(get_api_router(manager, db_manager, legacy_db_manager))
    app.include_router(get_websocket_router(manager))

    return app
