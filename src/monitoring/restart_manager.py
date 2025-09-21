# src/monitoring/restart_manager.py
import os
import sys
import time
import threading
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RestartManager:
    """Менеджер для безопасного перезапуска приложения"""

    def __init__(self):
        self.restart_requested = False
        self.restart_delay = 3  # секунд задержки перед перезапуском

    def request_restart(self, reason: str = "Health check failure"):
        """Запрашивает перезапуск приложения"""
        if self.restart_requested:
            logger.warning("Перезапуск уже запрошен, игнорируем повторный запрос")
            return

        self.restart_requested = True
        logger.critical(f"Запрошен перезапуск приложения. Причина: {reason}")

        # Запускаем перезапуск в отдельном потоке
        restart_thread = threading.Thread(
            target=self._perform_restart,
            args=(reason,),
            daemon=True,
            name="RestartThread"
        )
        restart_thread.start()

    def _perform_restart(self, reason: str):
        """Выполняет перезапуск приложения"""
        try:
            logger.info(f"Начинается процедура перезапуска через {self.restart_delay} секунд...")
            logger.info(f"Причина перезапуска: {reason}")

            # Даем время для завершения текущих запросов
            time.sleep(self.restart_delay)

            logger.info("Выполняется перезапуск приложения...")

            # Получаем параметры для перезапуска
            python_executable = sys.executable
            script_path = sys.argv[0]

            # Логируем команду перезапуска
            restart_command = f'"{python_executable}" "{script_path}"'
            logger.info(f"Команда перезапуска: {restart_command}")

            # Перезапускаем приложение
            os.execv(python_executable, [python_executable] + sys.argv)

        except Exception as e:
            logger.error(f"Ошибка при перезапуске приложения: {e}")
            logger.critical("Перезапуск не удался, приложение может быть в нерабочем состоянии")

            # В крайнем случае - принудительный выход
            logger.critical("Выполняется принудительный выход из приложения")
            os._exit(1)


# Глобальный экземпляр менеджера перезапуска
restart_manager = RestartManager()