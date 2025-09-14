# src/monitoring/health_monitor.py
import psutil
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class HealthMonitor:
    """Внутренний монитор состояния сервера с автоперезапуском"""

    def __init__(self, restart_callback=None):
        self.restart_callback = restart_callback
        self.last_request_time: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None
        self.last_self_test: Optional[datetime] = None
        self.start_time = datetime.now()
        self.request_count = 0
        self.health_check_count = 0
        self.self_test_failures = 0
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None

        # Настройки мониторинга
        self.health_check_interval = 60  # проверка каждую минуту
        self.self_test_interval = 300  # self-test каждые 5 минут
        self.max_memory_mb = 500  # лимит памяти в МБ
        self.max_uptime_hours = 24  # максимальное время работы без перезапуска
        self.max_self_test_failures = 3  # максимум неудачных self-test подряд

        # Счетчики проблем
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3

        logger.info("HealthMonitor инициализирован")

    def start_monitoring(self):
        """Запускает мониторинг в отдельном потоке"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="HealthMonitor"
        )
        self.monitor_thread.start()
        logger.info("Мониторинг здоровья и состояния запущен")

    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.is_monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        logger.info("Мониторинг состояния остановлен")

    def record_request(self):
        """Записывает время последнего успешного запроса"""
        self.last_request_time = datetime.now()
        self.request_count += 1

        # Сбрасываем счетчик проблем при успешном запросе
        if self.consecutive_failures > 0:
            logger.info(f"Сервер восстановился после {self.consecutive_failures} проблем")
            self.consecutive_failures = 0

    def get_health_status(self) -> Dict[str, Any]:
        """Возвращает текущее состояние здоровья сервера"""
        now = datetime.now()
        uptime = now - self.start_time

        # Проверяем память
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024

        # Проверяем время последнего self-test
        time_since_last_self_test = None
        if self.last_self_test:
            time_since_last_self_test = (now - self.last_self_test).total_seconds()

        status = {
            "status": "healthy",
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime.total_seconds(),
            "memory_mb": round(memory_mb, 2),
            "request_count": self.request_count,
            "health_check_count": self.health_check_count,
            "self_test_failures": self.self_test_failures,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
            "last_self_test": self.last_self_test.isoformat() if self.last_self_test else None,
            "time_since_last_self_test": time_since_last_self_test,
            "consecutive_failures": self.consecutive_failures
        }

        # Определяем проблемы
        problems = []

        if memory_mb > self.max_memory_mb:
            problems.append(f"Высокое потребление памяти: {memory_mb:.1f}MB")

        if uptime.total_seconds() > self.max_uptime_hours * 3600:
            problems.append(f"Долгая работа без перезапуска: {uptime.total_seconds() / 3600:.1f}ч")

        if self.self_test_failures >= self.max_self_test_failures:
            problems.append(f"Множественные сбои self-test: {self.self_test_failures}")

        if self.consecutive_failures >= self.max_consecutive_failures:
            problems.append(f"Множественные сбои health-check: {self.consecutive_failures}")

        if problems:
            status["status"] = "unhealthy"
            status["problems"] = problems

        return status

    def _monitoring_loop(self):
        """Основной цикл мониторинга"""

        while self.is_monitoring:
            try:
                self._perform_health_check()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(10)  # Короткая пауза при ошибке

    def _perform_health_check(self):
        """Выполняет проверку здоровья"""
        self.last_health_check = datetime.now()
        self.health_check_count += 1

        try:
            # Выполняем self-test каждые N минут
            if self._should_perform_self_test():
                self._perform_self_test()

            status = self.get_health_status()

            if status["status"] == "unhealthy":
                self.consecutive_failures += 1
                logger.warning(f"Обнаружены проблемы со здоровьем: {status['problems']}")

                # Решаем нужен ли перезапуск
                if self._should_restart(status):
                    logger.critical("Инициируется перезапуск сервера")
                    self._trigger_restart(status)
            else:
                # Сбрасываем счетчик при успешной проверке
                if self.consecutive_failures > 0:
                    logger.info(f"Health check восстановлен после {self.consecutive_failures} сбоев")
                    self.consecutive_failures = 0

                # Логируем состояние периодически
                if self.health_check_count % 10 == 0:  # каждые 10 проверок
                    logger.info(f"Сервер здоров. Uptime: {status['uptime_seconds'] / 3600:.1f}ч, "
                                f"Memory: {status['memory_mb']}MB, Requests: {status['request_count']}, "
                                f"Self-test failures: {status['self_test_failures']}")

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Ошибка при проверке здоровья: {e}")

    def _should_perform_self_test(self) -> bool:
        """Определяет нужно ли выполнять self-test"""
        if not self.last_self_test:
            return True

        time_since_last_test = (datetime.now() - self.last_self_test).total_seconds()
        return time_since_last_test >= self.self_test_interval

    def _perform_self_test(self):
        """Выполняет self-test сервера - проверяет что сервер может отвечать на запросы"""
        import requests
        import socket

        self.last_self_test = datetime.now()

        try:
            # Проверяем что порт открыт и слушает
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('127.0.0.1', 80))  # или другой порт
            sock.close()

            if result != 0:
                raise ConnectionError("Сервер не отвечает на локальном порту")

            # Пытаемся сделать HTTP запрос к health endpoint
            response = requests.get('http://127.0.0.1:80/health', timeout=10)

            if response.status_code != 200:
                raise ConnectionError(f"Health endpoint вернул код {response.status_code}")

            # Проверяем что можем получить данные
            data = response.json()
            if data.get('status') != 'ok':
                raise ConnectionError("Health endpoint вернул неверные данные")

            # Self-test успешен - сбрасываем счетчик
            if self.self_test_failures > 0:
                logger.info(f"Self-test восстановлен после {self.self_test_failures} сбоев")
                self.self_test_failures = 0

            logger.debug("Self-test успешен")

        except Exception as e:
            self.self_test_failures += 1
            logger.error(f"Self-test #{self.self_test_failures} неудачен: {e}")

            # Если много сбоев подряд - это серьезная проблема
            if self.self_test_failures >= self.max_self_test_failures:
                logger.critical(f"Self-test сбоит {self.self_test_failures} раз подряд - сервер не отвечает!")

    def _should_restart(self, status: Dict[str, Any]) -> bool:
        """Определяет нужен ли перезапуск"""
        # Критические условия для перезапуска
        critical_conditions = [
            self.consecutive_failures >= self.max_consecutive_failures,
            status.get("memory_mb", 0) > self.max_memory_mb * 2,  # Критический расход памяти
            status.get("uptime_seconds", 0) > self.max_uptime_hours * 3600,  # Долгая работа
            self.self_test_failures >= self.max_self_test_failures,  # Сервер не отвечает
        ]

        return any(critical_conditions)

    def _trigger_restart(self, status: Dict[str, Any]):
        """Запускает процедуру перезапуска"""
        logger.critical("=== ИНИЦИИРОВАН ПЕРЕЗАПУСК СЕРВЕРА ===")
        logger.critical(f"Причины: {status.get('problems', [])}")
        logger.critical(f"Статистика: Memory={status.get('memory_mb')}MB, "
                        f"Uptime={status.get('uptime_seconds', 0) / 3600:.1f}ч, "
                        f"Failures={self.consecutive_failures}")

        if self.restart_callback:
            try:
                # Останавливаем мониторинг перед перезапуском
                self.is_monitoring = False
                self.restart_callback("Health check failure")
            except Exception as e:
                logger.error(f"Ошибка при выполнении перезапуска: {e}")
        else:
            logger.critical("Callback для перезапуска не установлен!")

    def force_health_check(self) -> Dict[str, Any]:
        """Принудительная проверка здоровья (для endpoint)"""
        status = self.get_health_status()
        logger.info(f"Принудительная проверка здоровья: {status['status']}")
        return status


# Глобальный экземпляр монитора
health_monitor = HealthMonitor()