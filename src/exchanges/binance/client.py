# src/exchanges/binance/client.py
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Optional, Dict, Any
from src.utils.logger import get_logger
from ..base_exchange import BaseExchange
from ..retry_handler import retry_on_api_error
from ..quantity_calculator import QuantityCalculator
from .config import BinanceConfig


class BinanceClient(BaseExchange, QuantityCalculator):
    """Клиент для работы с Binance биржей"""

    def __init__(self, api_key: str, secret: str, testnet: bool, position_size: float, leverage: int):
        BaseExchange.__init__(self, "Binance")
        QuantityCalculator.__init__(self, leverage)

        self.config = BinanceConfig(api_key, secret, testnet, position_size, leverage)
        self.logger = get_logger(__name__)

        self.client = Client(
            api_key=self.config.api_key,
            api_secret=self.config.secret,
            testnet=self.config.testnet
        )

        # Устанавливаем URL для testnet если нужно
        if self.config.testnet:
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

    def _fetch_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """Получает информацию об инструменте с Binance API"""
        try:
            exchange_info = self.client.futures_exchange_info()

            symbol_info = None
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    symbol_info = s
                    break

            if not symbol_info:
                raise RuntimeError(f"Символ {symbol} не найден")

            info = {
                'qty_precision': symbol_info.get('quantityPrecision', 3),
                'price_precision': symbol_info.get('pricePrecision', 2),
                'qty_step': None,
                'min_qty': None,
                'tick_size': None
            }

            # Проходим по фильтрам
            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'LOT_SIZE':
                    info['qty_step'] = float(filter_item['stepSize'])
                    info['min_qty'] = float(filter_item['minQty'])
                elif filter_item['filterType'] == 'PRICE_FILTER':
                    info['tick_size'] = float(filter_item['tickSize'])

            # Устанавливаем плечо для этого символа
            self._setup_leverage(symbol)

            return info

        except Exception as e:
            self.logger.error(f"Ошибка получения информации об инструменте {symbol}: {e}")
            raise

    def _setup_leverage(self, symbol: str):
        """Устанавливает плечо для символа"""
        try:
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=self.config.leverage
            )
            self.logger.info(f"Плечо установлено {self.config.leverage}x для {symbol}")

        except BinanceAPIException as e:
            if e.code == -4028:
                self.logger.info(f"Плечо уже установлено {self.config.leverage}x для {symbol}")
            else:
                self.logger.error(f"Ошибка установки плеча для {symbol}: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка установки плеча для {symbol}: {e}")

    @retry_on_api_error()
    def get_account_balance(self, currency: str) -> float:
        """Получает баланс аккаунта для указанной валюты"""
        account = self.client.futures_account()

        for asset in account['assets']:
            if asset['asset'] == currency:
                return float(asset['walletBalance'])
        return 0.0

    @retry_on_api_error()
    def get_current_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Получает текущую позицию по символу"""
        positions = self.client.futures_position_information(symbol=symbol)

        if positions:
            position = positions[0]
            size = abs(float(position['positionAmt']))

            if size > 0:
                side = "Buy" if float(position['positionAmt']) > 0 else "Sell"
                return {
                    'side': side,
                    'size': size,
                    'entry_price': float(position['entryPrice']),
                    'unrealized_pnl': float(position['unRealizedProfit'])
                }
        return None

    @retry_on_api_error()
    def get_current_price(self, symbol: str) -> float:
        """Получает текущую цену символа"""
        ticker = self.client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])

    def open_long_position(self, symbol: str, position_size: float) -> bool:
        """Открывает длинную позицию"""
        return self._open_position(symbol, "BUY", position_size)

    def open_short_position(self, symbol: str, position_size: float) -> bool:
        """Открывает короткую позицию"""
        return self._open_position(symbol, "SELL", position_size)

    @retry_on_api_error()
    def _open_position(self, symbol: str, side: str, position_size: float) -> bool:
        """Открывает позицию"""
        current_price = self.get_current_price(symbol)
        if current_price == 0:
            self.logger.error(f"Не удалось получить цену для {symbol}")
            return False

        # Проверяем баланс
        quote_currency = self.extract_quote_currency(symbol)
        balance = self.get_account_balance(quote_currency)
        if balance < position_size:
            self.logger.error(f"Недостаточно средств {quote_currency}. Требуется: {position_size}, доступно: {balance}")
            return False

        # Используем общий метод расчета количества
        quantity = self.calculate_quantity(symbol, position_size, current_price)

        # Валидация количества
        if not self.validate_quantity(quantity, symbol):
            return False

        self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )

        direction = "Long" if side == "BUY" else "Short"
        self.logger.info(f"Открыта {direction} позиция {symbol}: {position_size} по {current_price}")
        return True

    @retry_on_api_error()
    def close_position(self, symbol: str) -> bool:
        """Закрывает текущую позицию по символу"""
        position = self.get_current_position(symbol)
        if not position:
            return True  # Позиции нет, считаем что закрыто

        opposite_side = "SELL" if position['side'] == "Buy" else "BUY"
        rounded_size = self.round_quantity(position['size'], symbol)

        self.client.futures_create_order(
            symbol=symbol,
            side=opposite_side,
            type='MARKET',
            quantity=rounded_size,
            reduceOnly=True
        )

        self.logger.info(f"Закрыта {position['side']} позиция {symbol}, PnL: {position['unrealized_pnl']}")
        return True