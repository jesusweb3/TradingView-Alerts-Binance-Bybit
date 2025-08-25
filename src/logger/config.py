# src/logger/config.py
import logging
import os
from datetime import datetime


def setup_logger(name: str = __name__) -> logging.Logger:
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Формат без указания модуля
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Создаем файл лога по текущей дате
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_filename = f"{logs_dir}/{current_date}.log"

        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger