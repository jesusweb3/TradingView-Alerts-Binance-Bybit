# src/server/app.py
import requests
import subprocess
import socket
import time
import yaml
import os
import json
from typing import Set
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from src.logger.config import setup_logger
from src.strategies.strategy_manager import StrategyManager

logger = setup_logger(__name__)

app = FastAPI()


def load_config() -> dict:
    """Загружает конфигурацию из YAML файла"""
    config_path = "config.yaml"

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")

    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        logger.info("Конфигурация загружена из config.yaml")
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"Ошибка парсинга YAML файла: {e}")
    except Exception as e:
        raise ValueError(f"Ошибка загрузки конфигурации: {e}")


def get_allowed_ips() -> Set[str]:
    """Получает список разрешенных IP из конфигурации"""
    config = load_config()

    allowed_ips = config.get('server', {}).get('allowed_ips', [])

    if not allowed_ips:
        raise ValueError("В config.yaml не найдена секция server.allowed_ips или она пуста")

    logger.info(f"Загружено {len(allowed_ips)} разрешенных IP адресов")
    return set(allowed_ips)


def is_port_in_use(port: int) -> bool:
    """Проверяет занят ли порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True


def stop_services_on_port_80():
    """Останавливает службы Windows на порту 80"""
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
            pids_to_kill = set()

            for line in lines:
                if ':80 ' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids_to_kill.add(pid)

            # Завершаем процессы
            for pid in pids_to_kill:
                try:
                    subprocess.run(['taskkill', '/PID', pid, '/F'],
                                   capture_output=True, timeout=10)
                    logger.info(f"Процесс PID {pid} завершен")
                except Exception as e:
                    logger.warning(f"Не удалось завершить процесс PID {pid}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при завершении процессов: {e}")


def ensure_port_80_free():
    """Обеспечивает освобождение порта 80"""
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


def get_server_ip():
    """Получает внешний IP сервера"""
    try:
        response = requests.get('https://ipinfo.io/ip', timeout=5)
        return response.text.strip()
    except requests.RequestException as e:
        logger.error(f"Не удалось получить внешний IP: {e}")
        raise RuntimeError("Ошибка получения внешнего IP сервера")


def get_client_ip(request: Request) -> str:
    """Получает IP клиента с учетом прокси"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host


# Загружаем разрешенные IP при старте
ALLOWED_IPS = get_allowed_ips()

# Инициализируем менеджер стратегий при старте
strategy_manager = StrategyManager()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Webhook endpoint для приема сигналов от TradingView"""
    try:
        # Проверяем IP адрес
        client_ip = get_client_ip(request)

        if client_ip not in ALLOWED_IPS:
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

        # Обрабатываем сигнал через менеджер стратегий
        result = strategy_manager.process_webhook_message(message)

        if result is None:
            return {"status": "ignored", "message": "Сигнал не распознан или отфильтрован"}

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка в webhook_handler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_server():
    logger.info("Запуск сервера")

    # Освобождаем порт 80
    ensure_port_80_free()

    # Показываем webhook URL
    server_ip = get_server_ip()
    logger.info(f"Ваш хук для TradingView: http://{server_ip}/webhook")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        log_level="error"
    )