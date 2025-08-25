# main.py
from src.logger.config import setup_logger
from src.server.app import start_server

if __name__ == "__main__":
    logger = setup_logger(__name__)
    logger.info("Trading Bot запущен")

    # Проверка конфигурации теперь происходит в StrategyManager и ExchangeManager
    start_server()