# src/server/app.py
import socket
import json
from typing import Set, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from src.logger.config import setup_logger
from src.config.manager import config_manager
from src.strategies.strategy_manager import StrategyManager

logger = setup_logger(__name__)

# Глобальные переменные для кеширования
_allowed_ips: Set[str] = set()
_strategy_manager: Optional[StrategyManager] = None


async def initialize_app():
    """Асинхронная инициализация приложения при старте"""
    global _allowed_ips, _strategy_manager

    try:
        # Кешируем конфигурацию при старте
        server_config = config_manager.get_server_config()
        _allowed_ips = set(server_config['allowed_ips'])
        logger.info(f"Загружено {len(_allowed_ips)} разрешенных IP адресов")

        # Инициализируем менеджер стратегий один раз
        _strategy_manager = StrategyManager()
        logger.info("Менеджер стратегий инициализирован")

    except Exception as e:
        logger.error(f"Ошибка инициализации приложения: {e}")
        raise


async def cleanup_app():
    """Очистка ресурсов при завершении приложения"""
    global _strategy_manager
    _strategy_manager = None
    logger.info("Ресурсы приложения очищены")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Управление жизненным циклом FastAPI приложения"""
    # Startup
    await initialize_app()
    yield
    # Shutdown
    await cleanup_app()


app = FastAPI(lifespan=lifespan)


def is_port_in_use(port: int) -> bool:
    """Проверяет занят ли порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True


def get_client_ip(request: Request) -> str:
    """Получает IP клиента с учетом прокси"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Webhook endpoint для приема сигналов от TradingView"""
    try:
        # Проверяем что менеджер стратегий инициализирован
        if _strategy_manager is None:
            logger.error("Менеджер стратегий не инициализирован")
            raise HTTPException(status_code=500, detail="Сервер не готов")

        # Проверяем IP адрес из кешированного списка
        client_ip = get_client_ip(request)

        if client_ip not in _allowed_ips:
            logger.warning(f"Запрос от неразрешенного IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Forbidden")

        # Получаем raw данные
        raw_body = await request.body()
        raw_text = raw_body.decode('utf-8')

        logger.info(f"Получен webhook от {client_ip}: {raw_text}")

        # Пытаемся парсить как JSON, иначе используем как plain text
        try:
            json_data = json.loads(raw_text)
            message = json_data.get('message') or json_data.get('text') or json_data.get('alert') or str(json_data)
        except (json.JSONDecodeError, ValueError):
            # Если не JSON, то это обычный текст
            message = raw_text.strip()

        if not message:
            logger.warning("В webhook нет текстового сообщения")
            return {"status": "error", "message": "Нет текстового сообщения"}

        # Обрабатываем сигнал через кешированный менеджер стратегий
        result = _strategy_manager.process_webhook_message(message)

        if result is None:
            return {"status": "ignored", "message": "Сигнал не распознан или отфильтрован"}

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка в webhook_handler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload-config")
async def reload_config():
    """Endpoint для перезагрузки конфигурации"""
    try:
        global _allowed_ips, _strategy_manager

        if _strategy_manager is None:
            logger.error("Менеджер стратегий не инициализирован")
            raise HTTPException(status_code=500, detail="Сервер не готов")

        # Перезагружаем конфигурацию
        config_manager.reload()

        # Обновляем кешированные данные
        server_config = config_manager.get_server_config()
        _allowed_ips = set(server_config['allowed_ips'])

        # Перезагружаем стратегии
        _strategy_manager.reload_config()

        logger.info("Конфигурация успешно перезагружена")
        return {"status": "success", "message": "Конфигурация перезагружена"}

    except Exception as e:
        logger.error(f"Ошибка перезагрузки конфигурации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_server_sync():
    """Синхронная функция запуска сервера"""
    logger.info("Запуск сервера")

    # Освобождаем порт 80 синхронно
    ensure_port_80_free()

    # Показываем webhook URL синхронно
    server_ip = get_server_ip()
    logger.info(f"Ваш хук для TradingView: http://{server_ip}/webhook")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        http="httptools",
        log_level="error"
    )


def ensure_port_80_free():
    """Обеспечивает освобождение порта 80"""
    import time

    if not is_port_in_use(80):
        logger.info("Порт 80 свободен")
        return

    logger.warning("Порт 80 занят, освобождаем...")

    # Шаг 1: Останавливаем службы
    stop_services_on_port_80()
    time.sleep(2)

    # Шаг 2: Проверяем освободился ли порт
    if not is_port_in_use(80):
        logger.info("Порт 80 освобожден после остановки служб")
        return

    # Шаг 3: Принудительно завершаем процессы
    kill_processes_on_port_80()
    time.sleep(2)

    # Шаг 4: Финальная проверка
    if is_port_in_use(80):
        raise RuntimeError("Не удалось освободить порт 80")

    logger.info("Порт 80 успешно освобожден")


def stop_services_on_port_80():
    """Останавливает службы Windows на порту 80"""
    import subprocess

    logger.info("Порт 80 занят, останавливаем веб-службы...")

    services_to_stop = ['w3svc', 'http', 'iisadmin']

    for service in services_to_stop:
        try:
            result = subprocess.run(
                ['net', 'stop', service],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info(f"Служба {service} остановлена")
            else:
                logger.warning(f"Не удалось остановить службу {service}: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Таймаут при остановке службы {service}")
        except Exception as e:
            logger.warning(f"Ошибка при остановке службы {service}: {e}")


def kill_processes_on_port_80():
    """Принудительно завершает процессы на порту 80"""
    import subprocess

    logger.info("Принудительное завершение процессов на порту 80...")

    try:
        # Получаем список процессов на порту 80
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.split('\n')
            pids_to_terminate = set()

            for line in lines:
                if ':80 ' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids_to_terminate.add(pid)

            # Завершаем процессы
            for pid in pids_to_terminate:
                try:
                    subprocess.run(['taskkill', '/PID', pid, '/F'],
                                   capture_output=True, timeout=10)
                    logger.info(f"Процесс PID {pid} завершен")
                except Exception as e:
                    logger.warning(f"Не удалось завершить процесс PID {pid}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при завершении процессов: {e}")


def get_server_ip():
    """Получает внешний IP сервера"""
    import requests

    try:
        response = requests.get('https://ipinfo.io/ip', timeout=5)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Не удалось получить внешний IP: {e}")
        raise RuntimeError("Ошибка получения внешнего IP сервера")