# main.py
from src.logger.config import setup_logger
from src.server.app import start_server_sync

if __name__ == "__main__":
    logger = setup_logger(__name__)
    logger.info("Trading Bot запущен")

    start_server_sync()