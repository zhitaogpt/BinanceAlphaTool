"""Async backend Binance trading loop supporting configurable tokens and order polling."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import logging
import signal
import sys
import time
import uuid
from decimal import Decimal, InvalidOperation, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BINANCE_QUOTE_URL = "https://www.binance.com/bapi/defi/v1/private/wallet-direct/swap/cex/get-quote"
BINANCE_BUY_URL = "https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/buy/pre/payment"
BINANCE_SELL_URL = "https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/sell/pre/payment"
BINANCE_OTO_ORDER_URL = "https://www.binance.com/bapi/asset/v1/private/alpha-trade/oto-order/place"
BINANCE_BALANCE_URL = (
    "https://www.binance.com/bapi/asset/v2/private/asset-service/wallet/balance"
    "?quoteAsset=BTC&needBalanceDetail=true&needEuFuture=true"
)
BINANCE_ORDER_STATUS_URL = "https://www.binance.com/bapi/defi/v1/private/wallet-direct/swap/cex/query-order"
BINANCE_ORDER_TRADES_URL = "https://www.binance.com/bapi/defi/v1/private/alpha-trade/order/get-user-trades"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
DEFAULT_REFERER = "https://www.binance.com/"

REQUEST_TIMEOUT_SECONDS = 15.0
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRY_BACKOFF_SECONDS = 2.0


@dataclass
class TradeConfig:
    """Runtime configuration for the backend trader."""

    from_token: str = "USDT"
    to_token: str = "KOGE"
    contract_address: str = "0xe6df05ce8c8301223373cf5b969afcb1498c5528"
    from_chain_id: str = "56"
    to_chain_id: str = "56"
    buy_amount: float = 10.0
    buy_price: Optional[float] = 48.00313932
    sell_target_amount: float = 10.1
    max_cycles: int = 1
    min_usdt_required: float = 10.0
    cycle_interval_seconds: float = 60.0
    retry_delay_seconds: float = 30.0
    fill_poll_interval_seconds: float = 10.0
    fill_timeout_seconds: float = 60.0 *10
    alpha_base_asset: Optional[str] = "ALPHA_22"
    alpha_payment_wallet_type: str = "CARD"
    alpha_pending_price_discount: float = 0.0005
    reduce_logging: bool = True


@dataclass
class TradeRecord:
    time: float
    buy_amount: float
    sell_amount: float
    profit_loss: float
    cycle_number: int


@dataclass
class TradingStats:
    start_balance: float = 0.0
    current_balance: float = 0.0
    total_volume: float = 0.0
    cycles_completed: int = 0
    total_profit: float = 0.0
    trade_history: List[TradeRecord] = field(default_factory=list)
    start_time: float = 0.0
    last_updated: float = 0.0

class BinanceTradingService:
    """Async counterpart of the original Pinia trading service."""

    def __init__(
        self,
        config: TradeConfig,
        auth_cookies: Dict[str, str],
        *,
        extra_headers: Optional[Dict[str, str]] = None,
        proxies: Optional[Dict[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if "cr00" not in auth_cookies:
            raise ValueError("auth_cookies must contain the cr00 cookie")

        self.config = config
        self.stats = TradingStats()
        self.logs: List[str] = []
        self._running = False
        self._lock = asyncio.Lock()
        self.extra_headers = extra_headers or {}
        self.proxies = proxies if proxies is not None else self._detect_proxies()

        if client is not None:
            self.client = client
            self._owns_client = False
        else:
            if self.proxies:
                self._apply_proxy_environment(self.proxies)
            self.client = httpx.AsyncClient(
                cookies=auth_cookies,
                timeout=REQUEST_TIMEOUT_SECONDS,
                trust_env=True
            )
            self._owns_client = True
        self.client.cookies.update(auth_cookies)

        self.logger = logger or logging.getLogger("BinanceTradingService")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(handler)
        self.logger.propagate = False

        self._log(f"service initialised with config: {self.config}", force=True)

    @staticmethod
    def _detect_proxies() -> Optional[Dict[str, str]]:
        env = os.environ
        proxies: Dict[str, str] = {}
        http_proxy = env.get('http_proxy') or env.get('HTTP_PROXY')
        https_proxy = env.get('https_proxy') or env.get('HTTPS_PROXY')
        all_proxy = env.get('all_proxy') or env.get('ALL_PROXY')
        if http_proxy:
            proxies['http'] = http_proxy
        if https_proxy:
            proxies['https'] = https_proxy
        elif all_proxy:
            proxies['https'] = all_proxy
        if all_proxy and 'http' not in proxies:
            proxies['http'] = all_proxy
        return proxies or None

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_proxy_environment(proxies: Dict[str, str]) -> None:
        for scheme, value in proxies.items():
            lower = f"{scheme}_proxy"
            upper = lower.upper()
            os.environ[lower] = value
            os.environ[upper] = value
        if 'all_proxy' not in proxies and 'http' in proxies and 'https' not in proxies:
            os.environ['https_proxy'] = proxies['http']
            os.environ['HTTPS_PROXY'] = proxies['http']

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _csrftoken(self) -> str:
        token = self.client.cookies.get("csrfToken")
        if token:
            return token
        cr00 = self.client.cookies.get("cr00")
        if not cr00:
            raise RuntimeError("cr00 cookie missing; cannot compute csrftoken")
        try:
            return hashlib.md5(cr00.encode("utf-8"), usedforsecurity=False).hexdigest()
        except TypeError:  # pragma: no cover - compatibility for older OpenSSL bindings
            return hashlib.md5(cr00.encode("utf-8")).hexdigest()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": self.extra_headers.get("Accept-Language", "zh,zh-CN;q=0.9,en;q=0.8"),
            "Content-Type": "application/json",
            "User-Agent": self.extra_headers.get("User-Agent", DEFAULT_USER_AGENT),
            "Referer": self.extra_headers.get("Referer", DEFAULT_REFERER),
            "clienttype": self.extra_headers.get("clienttype", "web"),
            "csrftoken": self.extra_headers.get("csrftoken", self._csrftoken()),
        }
        for key, value in self.extra_headers.items():
            if key not in headers or key in {"csrftoken", "clienttype"}:
                headers[key] = value
        trace_id = str(uuid.uuid4())
        headers['x-trace-id'] = trace_id
        headers['x-ui-request-trace'] = trace_id
        return headers

    async def _request_with_retry(self, method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        attempts = max(1, REQUEST_RETRY_ATTEMPTS)
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                if method == "GET":
                    response = await self.client.get(url, headers=self._headers())
                else:
                    response = await self.client.post(url, json=payload, headers=self._headers())
                response.raise_for_status()
                data = response.json()
                self.logger.debug("%s %s -> %s", method, url, data)
                return data
            except httpx.HTTPStatusError as exc:  # pragma: no cover - retry logging only
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else 'unknown'
                body_text = exc.response.text if exc.response is not None else ''
                json_summary = None
                if exc.response is not None:
                    try:
                        json_summary = exc.response.json()
                    except ValueError:
                        json_summary = None
                log_message = (
                    f"{method} {url} failed (attempt {attempt}/{attempts}), status={status}: {exc} body={body_text}"
                )
                if json_summary is not None:
                    log_message += f" json={json_summary}"
                self._log(log_message, level=logging.WARNING)
                if attempt == attempts:
                    break
                await asyncio.sleep(REQUEST_RETRY_BACKOFF_SECONDS)
            except Exception as exc:  # pragma: no cover - retry logging only
                last_exc = exc
                self._log(
                    f"{method} {url} failed (attempt {attempt}/{attempts}): {exc}",
                    level=logging.WARNING,
                )
                if attempt == attempts:
                    break
                await asyncio.sleep(REQUEST_RETRY_BACKOFF_SECONDS)
        if last_exc:
            raise last_exc
        raise RuntimeError("request_with_retry returned without response")

    async def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug("POST %s payload=%s", url, payload)
        return await self._request_with_retry("POST", url, payload)

    async def _get(self, url: str) -> Dict[str, Any]:
        self.logger.debug("GET %s", url)
        return await self._request_with_retry("GET", url)






    def _build_order_payload(
        self,
        base: Dict[str, Any],
        quote: Optional[Dict[str, Any]],
        *,
        pay_method: str = "FUNDING_AND_SPOT",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}

        if isinstance(quote, dict):
            quote_fields = {
                'traceId',
                'clientTraceId',
                'quoteId',
                'orderId',
                'bizId',
                'matchBizNo',
                'matchBizType',
                'tradeType',
                'tradeBase',
                'tradeQuote',
                'orderType',
                'serialNo',
                'uniQuoteId',
                'quoteTime',
                'quoteExpireTime',
                'price',
                'payMethod',
            }
            for key, value in quote.items():
                if value in (None, '', {}):
                    continue
                if key in quote_fields:
                    payload[key] = value
            extra = quote.get('extra')
            if extra:
                if isinstance(extra, (dict, list)):
                    try:
                        payload['extra'] = json.dumps(extra, separators=(',', ':'))
                    except Exception:  # pragma: no cover - fallback
                        payload['extra'] = str(extra)
                else:
                    payload['extra'] = extra
            if 'payMethod' not in payload and quote.get('payMethod'):
                payload['payMethod'] = quote['payMethod']

        for key, value in base.items():
            if value is not None:
                payload[key] = value

        if 'payMethod' not in payload and pay_method:
            payload['payMethod'] = pay_method

        for amount_key in ('fromCoinAmount', 'toCoinAmount'):
            if amount_key in payload:
                value = payload[amount_key]
                if isinstance(value, str):
                    continue
                try:
                    payload[amount_key] = format(Decimal(str(value)), 'f')
                except (InvalidOperation, TypeError, ValueError):
                    payload[amount_key] = str(value)

        if 'traceId' not in payload:
            payload['traceId'] = str(uuid.uuid4())
        if 'clientTraceId' not in payload:
            payload['clientTraceId'] = payload['traceId']

        return payload

    def _as_decimal(self, value: Any) -> Optional[Decimal]:
        if value in (None, "", {}):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _format_decimal_str(self, value: Any) -> str:
        number = self._as_decimal(value)
        if number is None:
            return str(value)
        return format(number, "f")

    def _extract_decimal(self, source: Optional[Dict[str, Any]], keys: List[str]) -> Optional[Decimal]:
        if not isinstance(source, dict):
            return None
        for key in keys:
            if key in source:
                number = self._as_decimal(source.get(key))
                if number is not None:
                    return number
        return None

    def _resolve_limit_base_asset(self, *quotes: Optional[Dict[str, Any]]) -> Optional[str]:
        for quote in quotes:
            if isinstance(quote, dict):
                for key in ("tradeBase", "baseAsset", "workingBaseAsset"):
                    value = quote.get(key)
                    if value:
                        return str(value)
        return self.config.alpha_base_asset

    def _resolve_limit_pending_price(
        self,
        working_price: Decimal,
        sell_quote: Optional[Dict[str, Any]],
    ) -> Decimal:
        candidate = self._extract_decimal(
            sell_quote,
            [
                "price",
                "pendingPrice",
                "expectedPrice",
            ],
        )
        return candidate if candidate is not None else working_price

    # ------------------------------------------------------------------
    # Binance API wrappers

    # ------------------------------------------------------------------
    async def get_quote(self, params: Dict[str, Any], *, label: str) -> Optional[Dict[str, Any]]:
        try:
            self._log(f"requesting {label} quote: {params}")
            data = await self._post(BINANCE_QUOTE_URL, params)
            quote = data.get("data")
            self._log(f"received {label} quote data: {data}")
            return quote
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"{label} quote failure: {exc}", level=logging.WARNING)
            return None

    async def buy_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._log(f"placing buy: {params}")
            result = await self._post(BINANCE_BUY_URL, params)
            self._log(f"buy response: {result}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"buy failure: {exc}", level=logging.ERROR)
            return {"success": False, "message": str(exc)}

    async def sell_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._log(f"placing sell: {params}")
            result = await self._post(BINANCE_SELL_URL, params)
            self._log(f"sell response: {result}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"sell failure: {exc}", level=logging.ERROR)
            return {"success": False, "message": str(exc)}

    async def place_limit_reverse_order(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._log(f"placing limit reverse order: {params}")
            result = await self._post(BINANCE_OTO_ORDER_URL, params)
            self._log(f"limit reverse order response: {result}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"limit reverse order failure: {exc}", level=logging.ERROR)
            return {"success": False, "message": str(exc)}

    async def get_order_trades(self, order_id: Any, symbol: str) -> Optional[List[Dict[str, Any]]]:
        if not order_id or not symbol:
            return None
        try:
            params = {"orderId": str(order_id), "symbol": symbol}
            url = f"{BINANCE_ORDER_TRADES_URL}?{urlencode(params)}"
            self._log(f"query order trades: {params}")
            data = await self._get(url)
            self._log(f"order trades response: {data}")
            if not isinstance(data, dict):
                return None
            if data.get("success") is False:
                self._log(f"order trades request unsuccessful: {data.get('message')}", level=logging.WARNING)
                return None
            trades = data.get("data")
            if isinstance(trades, list):
                return trades
            return None
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"order trades failure: {exc}", level=logging.WARNING)
            return None

    def _select_asset_entry(
        self,
        account_list: List[Dict[str, Any]],
        asset_symbol: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        asset_upper = (asset_symbol or "").upper()
        preferred_order = ("CARD", "MAIN", "SPOT")
        ordered_accounts: List[Dict[str, Any]] = []
        for account_type in preferred_order:
            account = next(
                (entry for entry in account_list if entry.get("accountType") == account_type),
                None,
            )
            if account and account not in ordered_accounts:
                ordered_accounts.append(account)
        for entry in account_list:
            if entry not in ordered_accounts:
                ordered_accounts.append(entry)
        for account in ordered_accounts:
            balances = account.get("assetBalances") or []
            candidate = next(
                (
                    asset
                    for asset in balances
                    if (asset.get("asset") or asset.get("coin")) == asset_upper
                ),
                None,
            )
            if candidate:
                return account, candidate
        return (ordered_accounts[0] if ordered_accounts else None), None

    def _extract_numeric_balance(self, asset_entry: Dict[str, Any]) -> float:
        free_value = (
            asset_entry.get("free")
            or asset_entry.get("availableBalance")
            or asset_entry.get("total")
            or 0.0
        )
        try:
            return float(Decimal(str(free_value)))
        except (InvalidOperation, TypeError, ValueError):
            self._log(f"unexpected balance payload: {asset_entry}", level=logging.WARNING)
            return 0.0

    async def get_usdt_balance(self) -> float:
        try:
            data = await self._get(BINANCE_BALANCE_URL)
            self._log(f"balance response: {data}")
            account_list = data.get("data") or []
            selected_account, usdt_info = self._select_asset_entry(account_list, "USDT")
            self._log(f"selected account data: {selected_account}")
            if not selected_account or not usdt_info:
                return 0.0
            balance = self._extract_numeric_balance(usdt_info)
            self._log(f"current MAIN USDT balance: {balance:.6f}")
            return balance
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"balance request failure: {exc}", level=logging.WARNING)
            return 0.0

    async def get_asset_balance(self, asset: str) -> float:
        symbol = (asset or "").upper()
        if not symbol:
            return 0.0
        try:
            data = await self._get(BINANCE_BALANCE_URL)
            account_list = data.get("data") or []
            self._log(f"loaded {len(account_list)} accounts while checking {symbol} balance")
            selected_account, asset_info = self._select_asset_entry(account_list, symbol)
            self._log(f"selected account for {symbol}: {selected_account}")
            if not asset_info:
                return 0.0
            balance = self._extract_numeric_balance(asset_info)
            self._log(f"current {symbol} balance: {balance:.6f}")
            return balance
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"{symbol} balance request failure: {exc}", level=logging.WARNING)
            return 0.0

    async def get_order_status(self, trace_id: str) -> Optional[Dict[str, Any]]:
        try:
            payload = {"traceId": trace_id}
            self._log(f"query order status: {payload}")
            data = await self._post(BINANCE_ORDER_STATUS_URL, payload)
            status = data.get("data")
            self._log(f"order status response: {status}")
            return status
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"order status failure: {exc}", level=logging.WARNING)
            return None

    # ------------------------------------------------------------------
    # Order lifecycle helpers
    # ------------------------------------------------------------------
    def _extract_trace_id(self, response: Dict[str, Any]) -> Optional[str]:
        candidates = [
            response.get("traceId"),
            response.get("orderId"),
            response.get("bizId"),
        ]
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        candidates.extend(
            [
                data.get("traceId"),
                data.get("orderId"),
                data.get("bizId"),
            ]
        )
        for value in candidates:
            if value:
                return str(value)
        return None

    async def wait_for_fill(self, trace_id: Optional[str], *, side: str) -> Optional[Dict[str, Any]]:
        if not trace_id:
            self._log(f"no trace id for {side} order; assuming immediate fill", level=logging.WARNING)
            return {"status": "FILLED"}

        deadline = time.time() + self.config.fill_timeout_seconds
        success_states = {"FILLED", "FINISHED", "SUCCESS", "COMPLETED", "EXECUTED", "TRIGGERED"}
        failure_states = {"REJECTED", "CANCELLED", "FAILED", "EXPIRED", "TERMINATED"}
        while time.time() < deadline:
            status = await self.get_order_status(trace_id)
            if status:
                order_status = status.get("orderStatus") or status.get("status")
                pending_status = status.get("pendingOrderStatus")
                if order_status in success_states and (pending_status is None or pending_status in success_states):
                    self._log(f"{side} order {trace_id} filled with status {order_status}")
                    return status
                if order_status in failure_states or (pending_status and pending_status in failure_states):
                    self._log(f"{side} order {trace_id} failed with status {order_status}", level=logging.ERROR)
                    return None
                self._log(f"{side} order {trace_id} still pending: {order_status}")
            if not self._running:
                self._log(f"stopping wait for {side} order {trace_id} as service is stopping")
                break
            await asyncio.sleep(self.config.fill_poll_interval_seconds)

        self._log(
            f"timed out waiting for {side} order {trace_id} to fill",
            level=logging.ERROR,
        )
        return None

    async def wait_for_limit_fill(
        self,
        order_ids: List[Optional[Any]],
        symbol: str,
    ) -> Optional[List[Dict[str, Any]]]:
        order_ids = [order_id for order_id in order_ids if order_id]
        if not order_ids:
            self._log("no valid order ids provided when waiting for limit fill", level=logging.ERROR)
            return None

        deadline = time.time() + self.config.fill_timeout_seconds
        while time.time() < deadline:
            for order_id in order_ids:
                trades = await self.get_order_trades(order_id, symbol)
                if trades:
                    self._log(
                        "limit order %s filled with %d trade(s)"
                        % (order_id, len(trades))
                    )
                    return trades
            await asyncio.sleep(self.config.fill_poll_interval_seconds)

        self._log(
            "timed out waiting for limit orders %s to fill"
            % ", ".join(str(oid) for oid in order_ids),
            level=logging.ERROR,
        )
        return None
    # ------------------------------------------------------------------
    # Trading loop
    # ------------------------------------------------------------------
    async def run_cycle(self) -> bool:
        usdt_balance = await self.get_usdt_balance()
        async with self._lock:
            self.stats.current_balance = usdt_balance

        required_balance = max(self.config.min_usdt_required, self.config.buy_amount)
        if usdt_balance < required_balance:
            self._log(
                "insufficient USDT balance: %.4f < %.4f"
                % (usdt_balance, required_balance),
                level=logging.WARNING,
            )
            return False

        starting_balance_decimal = self._as_decimal(usdt_balance) or Decimal("0")
        next_cycle = self.stats.cycles_completed + 1
        self._log(
            "starting cycle %d, buying %.4f %s"
            % (next_cycle, self.config.buy_amount, self.config.from_token),
            force=True,
        )

        buy_quote = await self.get_quote(
            {
                "fromToken": self.config.from_token,
                "fromBinanceChainId": self.config.from_chain_id,
                "fromCoinAmount": self.config.buy_amount,
                "toToken": self.config.to_token,
                "toBinanceChainId": self.config.to_chain_id,
                "toContractAddress": self.config.contract_address,
                "priorityMode": "priorityOnCustom",
                "customNetworkFeeMode": "priorityOnSuccess",
                "customSlippage": "0.001",
            },
            label="buy",
        )
        if not buy_quote:
            return False

        sell_quote = await self.get_quote(
            {
                "fromToken": self.config.to_token,
                "fromBinanceChainId": self.config.to_chain_id,
                "fromContractAddress": self.config.contract_address,
                "fromCoinAmount": buy_quote.get("toCoinAmount"),
                "toToken": self.config.from_token,
                "toBinanceChainId": self.config.from_chain_id,
                "toContractAddress": "",
                "priorityMode": "priorityOnCustom",
                "customNetworkFeeMode": "priorityOnSuccess",
                "customSlippage": "0.001",
            },
            label="sell",
        )
        working_quantity_raw = self._extract_decimal(
            buy_quote,
            [
                "filledAmount",
                "toCoinAmount",
                "workingQuantity",
                "quantity",
            ],
        )
        if working_quantity_raw is None or working_quantity_raw <= 0:
            self._log("unable to determine working quantity from quote", level=logging.ERROR)
            return False
        working_quantity = working_quantity_raw.quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)

        quote_payment_amount = self._extract_decimal(
            buy_quote,
            [
                "fromCoinAmount",
                "payAmount",
                "workingAmount",
            ],
        )
        if quote_payment_amount is None:
            quote_payment_amount = self._as_decimal(self.config.buy_amount) or Decimal("0")

        working_price_raw = self._extract_decimal(
            buy_quote,
            [
                "price",
                "workingPrice",
                "avgPrice",
            ],
        )
        if working_price_raw is None:
            try:
                working_price_raw = quote_payment_amount / working_quantity_raw
            except Exception:
                working_price_raw = Decimal("0")
        override_price = self._as_decimal(self.config.buy_price)
        working_price_candidate = override_price if override_price and override_price > 0 else working_price_raw
        if working_price_candidate is None or working_price_candidate <= 0:
            self._log("unable to resolve working price for limit order", level=logging.ERROR)
            return False
        working_price = working_price_candidate.quantize(Decimal("1.00000000"), rounding=ROUND_HALF_UP)
        if override_price and override_price > 0:
            self._log(
                "using configured working price %.8f %s"
                % (float(working_price), self.config.from_token)
            )

        payment_amount = working_price * working_quantity
        if payment_amount <= 0:
            payment_amount = quote_payment_amount
        else:
            try:
                payment_amount = payment_amount.quantize(Decimal("1.0000000000"), rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError):
                payment_amount = payment_amount

        base_asset = self._resolve_limit_base_asset(buy_quote, sell_quote)
        if not base_asset:
            self._log("unable to resolve base asset for limit order", level=logging.ERROR)
            return False

        discount_rate = self._as_decimal(getattr(self.config, "alpha_pending_price_discount", None))
        if discount_rate is None or discount_rate <= 0:
            pending_price_decimal = self._resolve_limit_pending_price(working_price, sell_quote)
        else:
            if discount_rate >= Decimal("1"):
                factor = Decimal("0")
            else:
                factor = Decimal("1") - discount_rate
            pending_price_decimal = working_price * factor
        if pending_price_decimal <= 0:
            pending_price_decimal = working_price
        pending_price = pending_price_decimal.quantize(Decimal("1.00000000"), rounding=ROUND_HALF_UP)
        quote_asset = (self.config.from_token or "USDT").upper()
        payment_wallet_type = (self.config.alpha_payment_wallet_type or "CARD").upper()
        trace_id = str(uuid.uuid4())
        limit_payload = {
            "baseAsset": base_asset,
            "quoteAsset": quote_asset,
            "workingSide": "BUY",
            "workingPrice": self._format_decimal_str(working_price),
            "workingQuantity": self._format_decimal_str(working_quantity),
            "pendingPrice": self._format_decimal_str(pending_price),
            "pendingSide": "SELL",
            "paymentDetails": [
                {
                    "amount": self._format_decimal_str(payment_amount),
                    "paymentWalletType": payment_wallet_type,
                }
            ],
            "traceId": trace_id,
            "clientTraceId": trace_id,
        }
        self._log(f"limit reverse order payload prepared: {limit_payload}")
        delay = random.uniform(1.0, 2.0)
        self._log(
            "delaying limit order submission by %.2f seconds to allow balance update"
            % delay
        )
        await asyncio.sleep(delay)
        limit_result = await self.place_limit_reverse_order(limit_payload)
        order_meta = limit_result.get("data") if isinstance(limit_result, dict) else {}
        working_order_id = order_meta.get("workingOrderId") if isinstance(order_meta, dict) else None
        pending_order_id = order_meta.get("pendingOrderId") if isinstance(order_meta, dict) else None
        if isinstance(limit_result, dict):
            success_flag = limit_result.get("success")
            code = str(limit_result.get("code", "")).upper() if limit_result.get("code") else ""
            if (isinstance(success_flag, bool) and not success_flag) or code not in ("", "SUCCESS", "000000", "0"):
                message = limit_result.get("message") or limit_result.get("msg") or "limit order rejected"
                self._log(f"limit reverse order rejected: {message}", level=logging.ERROR)
                return False
        else:
            self._log("unexpected response when placing limit order", level=logging.ERROR)
            return False

        symbol = f"{base_asset}{quote_asset}"
        trades = await self.wait_for_limit_fill([working_order_id, pending_order_id], symbol)
        if not trades:
            self._log("limit order fill failed; aborting cycle", level=logging.ERROR)
            return False

        selected_order_id: Optional[Any] = None
        trade_details: List[Dict[str, Any]] = trades
        for entry in trade_details:
            selected_order_id = entry.get("orderId") or selected_order_id
            self._log(
                "trade fill detail: order %s side=%s price=%s qty=%s quoteQty=%s commission=%s %s"
                % (
                    entry.get("orderId"),
                    entry.get("side"),
                    entry.get("price"),
                    entry.get("qty"),
                    entry.get("quoteQty"),
                    entry.get("commission"),
                    entry.get("commissionAsset"),
                )
            )

        total_qty = sum(
            (self._as_decimal(item.get("qty")) or Decimal("0")) for item in trade_details
        )
        total_quote = sum(
            (self._as_decimal(item.get("quoteQty")) or Decimal("0")) for item in trade_details
        )
        avg_fill_price = (
            total_quote / total_qty if total_qty and total_qty > 0 else Decimal("0")
        )

        order_fill: Dict[str, Any] = {
            "workingExecutedQuantity": str(total_qty),
            "workingExecutedQuoteQty": str(total_quote),
            "receivedAmount": str(total_quote),
            "pendingExecutedQuantity": str(total_qty),
            "pendingExecutedQuoteQty": str(total_quote),
        }
        balance_change = Decimal("0")  # placeholder, will recompute later
        loss_decimal = Decimal("0")
        loss_percent = Decimal("0")

        post_balance = await self.get_usdt_balance()
        post_balance_decimal = self._as_decimal(post_balance) or Decimal("0")
        profit_loss_decimal = post_balance_decimal - starting_balance_decimal

        balance_change = profit_loss_decimal
        loss_decimal = -balance_change if balance_change < 0 else Decimal("0")
        loss_percent = (
            (loss_decimal / starting_balance_decimal * Decimal("100"))
            if starting_balance_decimal > 0 and loss_decimal > 0
            else Decimal("0")
        )

        filled_quantity = self._extract_decimal(
            order_fill,
            [
                "workingExecutedQuantity",
                "workingFilledQuantity",
                "workingQuantity",
                "pendingExecutedQuantity",
                "filledQuantity",
            ],
        )
        if filled_quantity is None:
            filled_quantity = working_quantity

        spent_decimal = self._extract_decimal(
            order_fill,
            [
                "workingExecutedQuoteQty",
                "workingAmount",
                "workingQuoteAmount",
                "totalCost",
                "spentAmount",
            ],
        )
        if spent_decimal is None:
            spent_decimal = payment_amount

        realized_decimal = self._extract_decimal(
            order_fill,
            [
                "pendingExecutedQuoteQty",
                "pendingAmount",
                "pendingQuoteAmount",
                "realizedAmount",
                "receivedAmount",
            ],
        )
        if realized_decimal is None:
            realized_decimal = spent_decimal + profit_loss_decimal

        fill_loss_decimal = spent_decimal - realized_decimal
        if fill_loss_decimal < 0:
            fill_loss_decimal = Decimal("0")

        trade = TradeRecord(
            time=time.time(),
            buy_amount=float(spent_decimal),
            sell_amount=float(realized_decimal),
            profit_loss=float(profit_loss_decimal),
            cycle_number=next_cycle,
        )

        async with self._lock:
            self.stats.trade_history.append(trade)
            self.stats.total_volume += float(spent_decimal)
            self.stats.total_profit += float(profit_loss_decimal)
            self.stats.cycles_completed += 1
            self.stats.current_balance = float(post_balance_decimal)
            self.stats.last_updated = time.time()

        self._log(
            "cycle %d complete: limit order filled %.6f %s, P/L %.6f"
            % (
                trade.cycle_number,
                float(filled_quantity),
                self.config.to_token,
                trade.profit_loss,
            ),
            force=True,
        )
        self._log(
            "limit order summary: order=%s buy_target=%.8f %s, sell_target=%.8f %s, avg_fill=%.8f, quantity=%.8f %s, quote_spent=%.8f %s, balance_change=%.8f %s, loss=%.8f %s (%.4f%%)"
            % (
                selected_order_id or working_order_id or pending_order_id or "N/A",
                float(working_price),
                quote_asset,
                float(pending_price),
                quote_asset,
                float(avg_fill_price),
                float(total_qty),
                base_asset,
                float(total_quote),
                quote_asset,
                float(balance_change),
                quote_asset,
                float(loss_decimal),
                quote_asset,
                float(loss_percent),
            ),
            force=True,
        )
        summary_message = (
            "cycle %d summary: spent %.4f %s, loss %.6f %s"
            % (
                trade.cycle_number,
                float(spent_decimal),
                self.config.from_token,
                float(loss_decimal),
                self.config.from_token,
            )
            + ", balance change %.6f %s, loss rate %.4f%%"
            % (
                float(balance_change),
                self.config.from_token,
                float(loss_percent),
            )
        )
        self._log(summary_message, force=True)
        return True

    async def start(self) -> None:
        if self._running:
            self._log("trading already running")
            return

        self._running = True
        self.stats.start_time = time.time()
        self._log("trading loop started", force=True)

        try:
            while self._running:
                if 0 < self.config.max_cycles <= self.stats.cycles_completed:
                    self._log("maximum configured cycles reached, stopping")
                    break

                success = await self.run_cycle()
                if not success:
                    self._log("cycle failed; backing off before retry", force=True)
                    await asyncio.sleep(self.config.retry_delay_seconds)
                    continue

                await asyncio.sleep(self.config.cycle_interval_seconds)
        finally:
            await self.stop()

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._log("trading loop stopped", force=True)
        if self._owns_client:
            await self.client.aclose()

    def request_stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    def _log(self, message: str, *, level: int = logging.INFO, force: bool = False) -> None:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            safe_message = message.encode(encoding, errors="replace").decode(encoding)
        except LookupError:  # pragma: no cover - fallback for exotic encodings
            safe_message = message
        self.logs.append(safe_message)
        log_level = level
        if (
            not force
            and level == logging.INFO
            and getattr(self.config, "reduce_logging", False)
        ):
            log_level = logging.DEBUG
        self.logger.log(log_level, safe_message)

def _parse_cookie_header(raw: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        result[name] = value
    return result


def load_session_data(path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError("Cookie file is empty")

    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Cookie JSON must be an object")
        cookies_obj = data.get("cookies") if "cookies" in data or "headers" in data else data
        headers_obj = data.get("headers", {}) if "headers" in data else {}
        cookies = {str(k): str(v) for k, v in cookies_obj.items()}
        headers = {str(k): str(v) for k, v in headers_obj.items()}
        return cookies, headers

    cookies = _parse_cookie_header(text)
    return cookies, {}


def build_config_from_args(base: TradeConfig, args: argparse.Namespace) -> TradeConfig:
    data = base.__dict__.copy()
    if args.from_token:
        data["from_token"] = args.from_token
    if args.to_token:
        data["to_token"] = args.to_token
    if args.contract_address:
        data["contract_address"] = args.contract_address
    if args.buy_amount is not None:
        data["buy_amount"] = args.buy_amount
    if getattr(args, "buy_price", None) is not None:
        data["buy_price"] = args.buy_price
    if args.sell_amount is not None:
        data["sell_target_amount"] = args.sell_amount
    if args.cycles is not None:
        data["max_cycles"] = args.cycles
    if args.cycle_interval is not None:
        data["cycle_interval_seconds"] = args.cycle_interval
    if args.retry_delay is not None:
        data["retry_delay_seconds"] = args.retry_delay
    if args.fill_interval is not None:
        data["fill_poll_interval_seconds"] = args.fill_interval
    if args.fill_timeout is not None:
        data["fill_timeout_seconds"] = args.fill_timeout
    if getattr(args, "alpha_pending_discount", None) is not None:
        data["alpha_pending_price_discount"] = args.alpha_pending_discount
    if getattr(args, "verbose_logs", False):
        data["reduce_logging"] = False
    return TradeConfig(**data)


async def async_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Async Binance Alpha backend trader")
    parser.add_argument(
        "--cookies",
        required=True,
        help="Path to file that stores Binance cookies/headers (JSON map or raw Cookie header)",
    )
    parser.add_argument("--config", help="Path to config JSON file", default=None)
    parser.add_argument("--from-token", help="Token to swap from (default USDT)")
    parser.add_argument("--to-token", help="Token to swap to (default B2)")
    parser.add_argument("--contract-address", help="Destination token contract address")
    parser.add_argument("--buy-amount", type=float, help="Amount of from_token used per buy")
    parser.add_argument("--buy-price", type=float, help="Target working price for the reverse order (quote asset per base asset)")
    parser.add_argument("--sell-amount", type=float, help="Target from_token amount when selling")
    parser.add_argument("--cycles", type=int, help="Maximum number of cycles to execute (0 for infinite)")
    parser.add_argument("--cycle-interval", type=float, help="Seconds to wait between successful cycles")
    parser.add_argument("--retry-delay", type=float, help="Seconds to wait after a failed cycle")
    parser.add_argument("--fill-interval", type=float, help="Seconds between fill-status polls")
    parser.add_argument("--fill-timeout", type=float, help="Seconds to wait before giving up on a fill")
    parser.add_argument(
        "--alpha-pending-discount",
        type=float,
        help="Fractional discount applied to the limit order pending price (e.g. 0.001 for -0.1%)",
    )
    parser.add_argument(
        "--verbose-logs",
        action="store_true",
        help="Keep informational logs instead of degrading them to debug level",
    )
    parser.add_argument("--once", action="store_true", help="Run only a single cycle and exit")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    cookies, extra_headers = load_session_data(args.cookies)

    base_config = TradeConfig()
    if args.config:
        with open(args.config, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        base_config = TradeConfig(**data)

    config = build_config_from_args(base_config, args)

    service = BinanceTradingService(
        config=config,
        auth_cookies=cookies,
        extra_headers=extra_headers,
    )

    loop = asyncio.get_running_loop()

    def handle_signal(signum: int, frame: Optional[Any]) -> None:  # pylint: disable=unused-argument
        service._log(f"received signal {signum}; stopping", level=logging.INFO)
        service.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, service.request_stop)
        except NotImplementedError:
            signal.signal(sig, handle_signal)

    try:
        if args.once:
            await service.run_cycle()
            await service.stop()
        else:
            await service.start()
    finally:
        await service.stop()

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    sys.exit(main())
