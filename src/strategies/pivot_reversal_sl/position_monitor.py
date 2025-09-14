# src/strategies/pivot_reversal_sl/position_monitor.py
import time
import threading
from typing import Optional, Dict, Any
from src.logger.config import setup_logger
from src.config.manager import config_manager
from src.exchanges.binance.websocket_manager import BinanceWebSocketManager
from src.exchanges.binance.client import BinanceClient

logger = setup_logger(__name__)


class PositionMonitor:
    """Мониторинг позиции и управление stop-loss ордерами"""

    def __init__(self, binance_client: BinanceClient):
        self.binance_client = binance_client
        self.websocket_manager = BinanceWebSocketManager()

        # Состояние позиции
        self.symbol: Optional[str] = None
        self.position_data: Optional[Dict[str, Any]] = None
        self.stop_loss_order_id: Optional[str] = None
        self.is_monitoring = False

        # Загружаем настройки из конфигурации
        self._load_config()

        # Настраиваем callback для обновления цен
        self.websocket_manager.on_price_update = self._on_price_update

    def _load_config(self):
        """Загружает настройки из config.yaml"""
        try:
            config = config_manager.config
            sl_config = config.get('strategies', {}).get('pivot_reversal_sl', {})

            # Загружаем настройки с значениями по умолчанию
            self.pnl_threshold_percent = float(sl_config.get('pnl_threshold_percent', 5.0))
            self.stop_loss_percent = float(sl_config.get('stop_loss_percent', 1.2))
            self.price_difference_usdt = float(sl_config.get('price_difference_usdt', 1.0))
            self.position_fetch_delay = float(sl_config.get('position_fetch_delay', 5.0))

        except Exception as e:
            logger.warning(f"Ошибка загрузки настроек из конфига: {e}. Используем значения по умолчанию")
            # Значения по умолчанию
            self.pnl_threshold_percent = 5.0
            self.stop_loss_percent = 1.2
            self.price_difference_usdt = 1.0
            self.position_fetch_delay = 5.0

    def log_settings(self):
        """Выводит настройки мониторинга в лог"""
        logger.info(f"Настройки для мониторинга: "
                    f"PnL порог: {self.pnl_threshold_percent}%, "
                    f"Stop-loss: {self.stop_loss_percent}%, "
                    f"Разница цен: ${self.price_difference_usdt}, "
                    f"Задержка: {self.position_fetch_delay}с")

    def start_monitoring(self, symbol: str) -> bool:
        """
        Запускает мониторинг позиции для символа

        Args:
            symbol: Торговый символ (например, 'ETHUSDT')

        Returns:
            True если мониторинг запущен успешно
        """
        if self.is_monitoring:
            logger.warning(f"Мониторинг уже активен для {self.symbol}")
            return False

        self.symbol = symbol
        self.is_monitoring = True

        # Запускаем в отдельном потоке
        monitor_thread = threading.Thread(
            target=self._monitoring_thread,
            daemon=True,
            name=f"PositionMonitor-{symbol}"
        )
        monitor_thread.start()

        logger.info(f"Запущен мониторинг позиции для {symbol}")
        return True

    def stop_monitoring(self):
        """Останавливает мониторинг позиции"""
        if not self.is_monitoring:
            return

        self.is_monitoring = False

        # Останавливаем WebSocket
        self.websocket_manager.stop()

        # Отменяем активный stop-loss если есть
        if self.stop_loss_order_id:
            self._cancel_stop_loss_order()

        self._reset_state()
        logger.info(f"Мониторинг позиции остановлен для {self.symbol}")

    def has_active_stop_loss(self) -> bool:
        """
        Проверяет есть ли активный stop-loss ордер

        Returns:
            True если есть активный stop-loss
        """
        return self.stop_loss_order_id is not None

    def reload_config(self):
        """Перезагружает настройки из конфигурации"""
        config_manager.clear_cache()
        self._load_config()
        logger.info("Настройки PositionMonitor перезагружены")

    def _monitoring_thread(self):
        """Основной поток мониторинга"""
        try:
            # Ждем заполнения позиции
            logger.info(f"Ожидание заполнения позиции {self.position_fetch_delay} сек...")
            time.sleep(self.position_fetch_delay)

            # Получаем данные позиции
            if not self._fetch_position_data():
                logger.error("Не удалось получить данные позиции")
                return

            # Запускаем WebSocket для мониторинга цен
            if not self.websocket_manager.start(self.symbol):
                logger.error("Не удалось запустить WebSocket")
                return

            logger.info(f"Мониторинг активен. Entry: {self.position_data['entry_price']}, "
                        f"Size: {self.position_data['size']}, Side: {self.position_data['side']}")

            # Ждем пока мониторинг активен
            while self.is_monitoring:
                time.sleep(1)

        except Exception as e:
            logger.error(f"Ошибка в потоке мониторинга: {e}")
        finally:
            self.websocket_manager.stop()

    def _fetch_position_data(self) -> bool:
        """
        Получает данные текущей позиции с биржи

        Returns:
            True если данные получены успешно
        """
        try:
            position = self.binance_client.get_current_position(self.symbol)

            if not position:
                logger.error(f"Позиция не найдена для {self.symbol}")
                return False

            self.position_data = {
                'entry_price': float(position['entry_price']),
                'size': float(position['size']),
                'side': position['side'],  # 'Buy' или 'Sell'
                'margin_used': self._calculate_margin_used(
                    float(position['entry_price']),
                    float(position['size'])
                )
            }

            logger.info(f"Данные позиции получены: {self.position_data}")
            return True

        except Exception as e:
            logger.error(f"Ошибка получения данных позиции: {e}")
            return False

    def _calculate_margin_used(self, entry_price: float, size: float) -> float:
        """
        Рассчитывает использованную маржу

        Args:
            entry_price: Цена входа
            size: Размер позиции

        Returns:
            Размер использованной маржи
        """
        # Маржа = (entry_price * size) / leverage
        leverage = self.binance_client.config.leverage
        margin = (entry_price * size) / leverage
        return margin

    def _on_price_update(self, _symbol: str, current_price: float):
        """
        Обработчик обновления цены от WebSocket

        Args:
            _symbol: Символ (не используется)
            current_price: Текущая цена
        """
        if not self.is_monitoring or not self.position_data:
            return

        try:
            # Рассчитываем текущий PnL
            pnl_usdt = self._calculate_pnl(current_price)
            pnl_percent = self._calculate_pnl_percent(pnl_usdt)

            # Проверяем нужно ли выставить stop-loss
            if not self.stop_loss_order_id and pnl_percent >= self.pnl_threshold_percent:
                logger.info(f"PnL достиг {pnl_percent:.2f}% от маржи. Выставляем stop-loss")
                self._place_stop_loss_order()

            # Логируем состояние каждые 30 секунд
            if hasattr(self, '_last_log_time'):
                if time.time() - self._last_log_time > 30:
                    self._log_position_status(current_price, pnl_usdt, pnl_percent)
            else:
                self._last_log_time = time.time()

        except Exception as e:
            logger.error(f"Ошибка в обработчике цены: {e}")

    def _calculate_pnl(self, current_price: float) -> float:
        """
        Рассчитывает PnL в USDT

        Args:
            current_price: Текущая цена

        Returns:
            PnL в USDT
        """
        entry_price = self.position_data['entry_price']
        size = self.position_data['size']
        side = self.position_data['side']

        if side == 'Buy':
            # Long позиция: прибыль когда цена растет
            price_diff = current_price - entry_price
        else:
            # Short позиция: прибыль когда цена падает
            price_diff = entry_price - current_price

        pnl_usdt = price_diff * size
        return pnl_usdt

    def _calculate_pnl_percent(self, pnl_usdt: float) -> float:
        """
        Рассчитывает PnL в процентах от маржи

        Args:
            pnl_usdt: PnL в USDT

        Returns:
            PnL в процентах от маржи
        """
        margin_used = self.position_data['margin_used']
        pnl_percent = (pnl_usdt / margin_used) * 100
        return pnl_percent

    def _place_stop_loss_order(self):
        """Выставляет stop-loss ордер"""
        try:
            entry_price = self.position_data['entry_price']
            size = self.position_data['size']
            side = self.position_data['side']

            # Рассчитываем stop и limit цены
            if side == 'Buy':
                # Long позиция: stop-loss выше entry для фиксации прибыли
                stop_price = entry_price + (entry_price * self.stop_loss_percent / 100)
                limit_price = stop_price - self.price_difference_usdt
                order_side = 'SELL'
            else:
                # Short позиция: stop-loss ниже entry для фиксации прибыли
                stop_price = entry_price - (entry_price * self.stop_loss_percent / 100)
                limit_price = stop_price + self.price_difference_usdt
                order_side = 'BUY'

            # Округляем цены согласно требованиям биржи
            stop_price = self._round_price(stop_price)
            limit_price = self._round_price(limit_price)

            # Выставляем STOP_MARKET ордер
            response = self.binance_client.client.futures_create_order(
                symbol=self.symbol,
                side=order_side,
                type='STOP_MARKET',
                quantity=size,
                stopPrice=stop_price,
                price=limit_price,
                reduceOnly=True,
                timeInForce='GTC'
            )

            self.stop_loss_order_id = response['orderId']

            logger.info(f"Stop-loss выставлен: ID={self.stop_loss_order_id}, "
                        f"Stop={stop_price}, Limit={limit_price}, Side={order_side}")

        except Exception as e:
            logger.error(f"Ошибка выставления stop-loss: {e}")

    def _cancel_stop_loss_order(self) -> bool:
        """
        Отменяет активный stop-loss ордер

        Returns:
            True если отмена успешна
        """
        if not self.stop_loss_order_id:
            return True

        try:
            self.binance_client.client.futures_cancel_order(
                symbol=self.symbol,
                orderId=self.stop_loss_order_id
            )

            logger.info(f"Stop-loss отменен: ID={self.stop_loss_order_id}")
            self.stop_loss_order_id = None
            return True

        except Exception as e:
            logger.error(f"Ошибка отмены stop-loss: {e}")
            return False

    @staticmethod
    def _round_price(price: float) -> float:
        """
        Округляет цену согласно требованиям биржи

        Args:
            price: Исходная цена

        Returns:
            Округленная цена
        """
        # Для большинства пар достаточно 2 знаков после запятой
        # В будущем можно получать tick_size из instrument info
        return round(price, 2)

    def _log_position_status(self, current_price: float, pnl_usdt: float, pnl_percent: float):
        """Логирует текущее состояние позиции"""
        self._last_log_time = time.time()

        stop_status = f"Stop-loss: {'Активен' if self.stop_loss_order_id else 'Не выставлен'}"

        logger.info(f"{self.symbol} | Цена: {current_price} | "
                    f"PnL: {pnl_usdt:.2f}$ ({pnl_percent:.2f}%) | {stop_status}")

    def _reset_state(self):
        """Сбрасывает внутреннее состояние"""
        self.symbol = None
        self.position_data = None
        self.stop_loss_order_id = None
        if hasattr(self, '_last_log_time'):
            delattr(self, '_last_log_time')