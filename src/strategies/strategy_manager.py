# src/strategies/strategy_manager.py
from typing import Optional
from src.utils.logger import get_logger
from src.config.manager import config_manager
from .simple_strategy import SimpleStrategy

logger = get_logger(__name__)


class StrategyManager:
    """Менеджер для управления торговой стратегией"""

    def __init__(self):
        self.strategy: Optional[SimpleStrategy] = None
        self._initialize_strategy()

    def _initialize_strategy(self):
        """Инициализирует единственную торговую стратегию"""
        try:
            # Проверяем что торговля включена
            if not config_manager.is_trading_enabled():
                logger.warning("Торговля отключена в конфигурации")
                return

            # Создаем единственную стратегию
            self.strategy = SimpleStrategy()

            # Получаем символ для логирования
            symbol = config_manager.get_trading_symbol()

            logger.info(f"Стратегия инициализирована для символа: {symbol}")

        except Exception as e:
            logger.error(f"Ошибка инициализации стратегии: {e}")
            raise

    def process_webhook_message(self, message: str) -> Optional[dict]:
        """
        Обрабатывает сообщение от webhook

        Args:
            message: Сообщение от TradingView

        Returns:
            Словарь с результатом обработки или None если сигнал не обработан
        """
        if not self.strategy:
            logger.error("Стратегия не инициализирована или торговля отключена")
            return {"status": "error", "message": "Стратегия не инициализирована"}

        # Парсим сигнал
        signal = self.strategy.parse_message(message)
        if not signal:
            logger.info("Сигнал не распознан")
            return None

        # Проверяем фильтр дубликатов
        if not self.strategy.should_process_signal(signal):
            return {"status": "ignored", "message": "Сигнал отфильтрован как дубликат"}

        # Обрабатываем сигнал
        success = self.strategy.process_signal(signal)

        if success:
            symbol = config_manager.get_trading_symbol()
            return {
                "status": "success",
                "signal": {
                    "symbol": symbol,
                    "action": signal.action.value
                }
            }
        else:
            return {"status": "error", "message": "Ошибка обработки сигнала"}

    def reload_config(self):
        """Перезагружает конфигурацию и пересоздает стратегию"""
        try:
            config_manager.clear_cache()
            self.strategy = None
            self._initialize_strategy()
            logger.info("Конфигурация стратегии перезагружена")
        except Exception as e:
            logger.error(f"Ошибка перезагрузки конфигурации: {e}")
            raise