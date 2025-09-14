# src/exchanges/binance/websocket_manager.py
import asyncio
import json
import threading
from typing import Optional, Callable
from datetime import datetime
import websockets
from src.logger.config import setup_logger

logger = setup_logger(__name__)


class BinanceWebSocketManager:
    """Менеджер WebSocket подключения к Binance для получения цен в реальном времени"""

    def __init__(self):
        self.ws_url = "wss://fstream.binance.com/ws/"
        self.symbol: Optional[str] = None
        self.last_price: Optional[float] = None
        self.last_update: Optional[datetime] = None

        self._websocket = None
        self._loop = None
        self._thread = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5  # секунд

        # Callback для обновления цены (опционально)
        self.on_price_update: Optional[Callable[[str, float], None]] = None

    def start(self, symbol: str) -> bool:
        """
        Запускает WebSocket подключение для символа

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')

        Returns:
            True если запуск успешен
        """
        if self._is_running:
            logger.warning(f"WebSocket уже запущен для {self.symbol}")
            return False

        self.symbol = symbol.lower()  # Binance использует lowercase для WebSocket
        self._is_running = True

        # Запускаем в отдельном потоке чтобы не блокировать основное приложение
        self._thread = threading.Thread(
            target=self._run_websocket_thread,
            daemon=True,
            name=f"BinanceWS-{symbol}"
        )
        self._thread.start()

        logger.info(f"WebSocket запущен для {symbol}")
        return True

    def stop(self):
        """Останавливает WebSocket подключение"""
        if not self._is_running:
            return

        self._is_running = False

        # Закрываем WebSocket если есть
        if self._websocket and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._websocket.close(),
                self._loop
            )

        # Ждем завершения потока
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self._reset_state()
        logger.info(f"WebSocket остановлен для {self.symbol}")

    def get_last_price(self) -> Optional[float]:
        """
        Возвращает последнюю полученную цену

        Returns:
            Последняя цена или None если нет данных
        """
        return self.last_price

    def get_last_update(self) -> Optional[datetime]:
        """
        Возвращает время последнего обновления цены

        Returns:
            Время последнего обновления или None если нет данных
        """
        return self.last_update

    def is_connected(self) -> bool:
        """
        Проверяет активность подключения

        Returns:
            True если WebSocket активен и получает данные
        """
        if not self._is_running or not self.last_update:
            return False

        # Считаем отключенным если нет данных больше 30 секунд
        time_since_update = (datetime.now() - self.last_update).total_seconds()
        return time_since_update < 30

    def _run_websocket_thread(self):
        """Запускает event loop в отдельном потоке"""
        try:
            # Создаем новый event loop для этого потока
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Запускаем WebSocket
            self._loop.run_until_complete(self._websocket_loop())

        except Exception as e:
            logger.error(f"Ошибка в WebSocket потоке: {e}")
        finally:
            if self._loop:
                self._loop.close()

    async def _websocket_loop(self):
        """Основной цикл WebSocket подключения с переподключениями"""
        while self._is_running:
            try:
                await self._connect_and_listen()

            except Exception as e:
                logger.error(f"WebSocket ошибка: {e}")

                if self._is_running:
                    self._reconnect_attempts += 1

                    if self._reconnect_attempts <= self._max_reconnect_attempts:
                        logger.info(f"Переподключение через {self._reconnect_delay}с "
                                    f"(попытка {self._reconnect_attempts}/{self._max_reconnect_attempts})")
                        await asyncio.sleep(self._reconnect_delay)
                    else:
                        logger.error("Превышено максимальное количество попыток переподключения")
                        break

    async def _connect_and_listen(self):
        """Подключается к WebSocket и слушает сообщения"""
        # Формируем URL для ticker символа
        stream_name = f"{self.symbol}@ticker"
        url = f"{self.ws_url}{stream_name}"

        logger.info(f"Подключение к {url}")

        async with websockets.connect(url) as websocket:
            self._websocket = websocket
            self._reconnect_attempts = 0  # Сбрасываем счетчик при успешном подключении

            logger.info(f"WebSocket подключен для {self.symbol}")

            async for message in websocket:
                if not self._is_running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(f"Ошибка обработки сообщения: {e}")

    async def _process_message(self, message: str):
        """
        Обрабатывает входящее сообщение от WebSocket

        Args:
            message: JSON строка с данными ticker
        """
        try:
            data = json.loads(message)

            # Извлекаем цену из ticker данных
            if 'c' in data:  # 'c' - это close price (current price)
                price = float(data['c'])
                self.last_price = price
                self.last_update = datetime.now()

                # Вызываем callback если установлен
                if self.on_price_update:
                    try:
                        self.on_price_update(self.symbol.upper(), price)
                    except Exception as e:
                        logger.error(f"Ошибка в callback обновления цены: {e}")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Некорректные данные от WebSocket: {e}")

    def _reset_state(self):
        """Сбрасывает внутреннее состояние"""
        self.symbol = None
        self.last_price = None
        self.last_update = None
        self._websocket = None
        self._loop = None
        self._thread = None
        self._reconnect_attempts = 0