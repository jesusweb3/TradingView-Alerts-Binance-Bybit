# main.py
from src.logger.config import setup_logger
from src.server.app import start_server
from src.parser.strategy_parser import StrategyParser

if __name__ == "__main__":
    logger = setup_logger(__name__)
    logger.info("Trading Bot запущен")

    try:
        StrategyParser.validate_strategies()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации стратегий: {e}")
        exit(1)

    start_server()