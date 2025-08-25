# src/server/app.py
import requests
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from src.logger.config import setup_logger
from src.parser.strategy_parser import StrategyParser

logger = setup_logger(__name__)

app = FastAPI()

# Белый список IP адресов TradingView
ALLOWED_IPS = {
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
    "194.156.99.37"
}


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

        # Получаем JSON данные
        data = await request.json()
        logger.info(f"Получен webhook от {client_ip}: {data}")

        # Ищем поле с сообщением (может быть 'message', 'text' или другое)
        message = data.get('message') or data.get('text') or data.get('alert') or str(data)

        if not message:
            logger.warning("В webhook нет текстового сообщения")
            return {"status": "error", "message": "Нет текстового сообщения"}

        # Парсим сигнал
        signal = StrategyParser.parse(message)

        if signal is None:
            return {"status": "ignored", "message": "Сигнал не распознан или отфильтрован"}

        logger.info(f"Сигнал успешно обработан: {signal}")
        return {
            "status": "success",
            "signal": {
                "strategy": signal.strategy_name,
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "action": signal.action.value
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка в webhook_handler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_server():
    logger.info("Запуск сервера")

    # Показываем webhook URL
    server_ip = get_server_ip()
    logger.info(f"Ваш хук для TradingView: http://{server_ip}/webhook")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=80,
        log_level="error"
    )