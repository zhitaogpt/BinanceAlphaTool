"""Backend-only Binance Alpha trading loop inspired by the Vue service."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

BINANCE_QUOTE_URL = "https://www.binance.com/bapi/defi/v1/private/wallet-direct/swap/cex/get-quote"
BINANCE_BUY_URL = "https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/buy/pre/payment"
BINANCE_SELL_URL = "https://www.binance.com/bapi/defi/v2/private/wallet-direct/swap/cex/sell/pre/payment"
BINANCE_BALANCE_URL = (
    "https://www.binance.com/bapi/asset/v2/private/asset-service/wallet/balance"
    "?quoteAsset=USDT&needBalanceDetail=true&needEuFuture=true"
)


@dataclass
class TradeConfig:
    """Runtime configuration for the backend trader."""

    from_token: str = "USDT"
    to_token: str = "B2"
    contract_address: str = "0x783c3f003f172c6ac5ac700218a357d2d66ee2a2"
    from_chain_id: str = "56"
    to_chain_id: str = "56"
    buy_amount: float = 10.0
    sell_target_amount: float = 10.1
    max_cycles: int = 10
    min_usdt_required: float = 50.0
    cycle_interval_seconds: float = 60.0
    retry_delay_seconds: float = 30.0


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
    """Python translation of the original Pinia trading service."""

    def __init__(
        self,
        config: TradeConfig,
        auth_cookies: Dict[str, str],
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if "cr00" not in auth_cookies:
            raise ValueError("auth_cookies must contain the cr00 cookie")

        self.config = config
        self.stats = TradingStats()
        self.logs: List[str] = []
        self._running = False
        self._lock = threading.Lock()

        self.session = session or requests.Session()
        self.session.cookies.update(auth_cookies)
        self.logger = logger or logging.getLogger("BinanceTradingService")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(handler)

        self._log("service initialised with config: %s" % self.config)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        cr00 = self.session.cookies.get("cr00")
        if not cr00:
            raise RuntimeError("cr00 cookie missing; cannot compute csrftoken")
        csrftoken = hashlib.md5(cr00.encode("utf-8"), usedforsecurity=False).hexdigest()
        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "clienttype": "web",
            "csrftoken": csrftoken,
        }

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug("POST %s payload=%s", url, payload)
        response = self.session.post(url, json=payload, headers=self._headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        self.logger.debug("POST %s -> %s", url, data)
        return data

    def _get(self, url: str) -> Dict[str, Any]:
        self.logger.debug("GET %s", url)
        response = self.session.get(url, headers=self._headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        self.logger.debug("GET %s -> %s", url, data)
        return data

    # ------------------------------------------------------------------
    # Binance API wrappers
    # ------------------------------------------------------------------
    def get_quote(self, params: Dict[str, Any], *, label: str) -> Optional[Dict[str, Any]]:
        try:
            self._log(f"requesting {label} quote: {params}")
            data = self._post(BINANCE_QUOTE_URL, params)
            quote = data.get("data")
            self._log(f"received {label} quote: {quote}")
            return quote
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"{label} quote failure: {exc}", level=logging.WARNING)
            return None

    def buy_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._log(f"placing buy: {params}")
            result = self._post(BINANCE_BUY_URL, params)
            self._log(f"buy response: {result}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"buy failure: {exc}", level=logging.ERROR)
            return {"success": False, "message": str(exc)}

    def sell_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._log(f"placing sell: {params}")
            result = self._post(BINANCE_SELL_URL, params)
            self._log(f"sell response: {result}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"sell failure: {exc}", level=logging.ERROR)
            return {"success": False, "message": str(exc)}

    def get_usdt_balance(self) -> float:
        try:
            data = self._get(BINANCE_BALANCE_URL)
            account_list = data.get("data", [])
            main_account = next(
                (account for account in account_list if account.get("accountType") == "MAIN"),
                None,
            )
            if not main_account:
                return 0.0
            usdt = next(
                (asset for asset in main_account.get("assetBalances", []) if asset.get("asset") == "USDT"),
                None,
            )
            balance = float(usdt.get("free", 0.0)) if usdt else 0.0
            self._log(f"current MAIN USDT balance: {balance:.6f}")
            return balance
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"balance request failure: {exc}", level=logging.WARNING)
            return 0.0

    # ------------------------------------------------------------------
    # Trading loop
    # ------------------------------------------------------------------
    def run_cycle(self) -> bool:
        """Execute a single buy->sell cycle using configured amounts."""
        usdt_balance = self.get_usdt_balance()
        with self._lock:
            self.stats.current_balance = usdt_balance

        if usdt_balance < max(self.config.min_usdt_required, self.config.buy_amount):
            self._log(
                "insufficient USDT balance: %.4f < %.4f"
                % (usdt_balance, max(self.config.min_usdt_required, self.config.buy_amount)),
                level=logging.WARNING,
            )
            return False

        next_cycle = self.stats.cycles_completed + 1
        self._log(
            "starting cycle %d, buying %.4f %s"
            % (next_cycle, self.config.buy_amount, self.config.from_token)
        )

        buy_quote = self.get_quote(
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

        buy_result = self.buy_token(
            {
                "fromToken": self.config.from_token,
                "fromBinanceChainId": self.config.from_chain_id,
                "fromCoinAmount": self.config.buy_amount,
                "toToken": self.config.to_token,
                "toContractAddress": self.config.contract_address,
                "toCoinAmount": buy_quote.get("toCoinAmount"),
                "priorityMode": "priorityOnPrice",
                "extra": buy_quote.get("extra"),
            }
        )
        if not buy_result.get("success"):
            self._log(f"buy order rejected: {buy_result.get('message')}")
            return False

        bought_amount = float(buy_quote.get("toCoinAmount", 0.0))
        self._log(
            "buy filled: received %.6f %s"
            % (bought_amount, self.config.to_token)
        )

        sell_quote = self.get_quote(
            {
                "fromToken": self.config.to_token,
                "fromBinanceChainId": self.config.to_chain_id,
                "fromContractAddress": self.config.contract_address,
                "fromCoinAmount": bought_amount,
                "toToken": self.config.from_token,
                "toBinanceChainId": self.config.from_chain_id,
                "toContractAddress": "",
                "priorityMode": "priorityOnCustom",
                "customNetworkFeeMode": "priorityOnSuccess",
                "customSlippage": "0.001",
            },
            label="sell",
        )
        if not sell_quote:
            return False

        sell_result = self.sell_token(
            {
                "fromToken": self.config.to_token,
                "fromBinanceChainId": self.config.to_chain_id,
                "fromContractAddress": self.config.contract_address,
                "fromCoinAmount": bought_amount,
                "toToken": self.config.from_token,
                "toBinanceChainId": self.config.from_chain_id,
                "toCoinAmount": self.config.sell_target_amount,
                "priorityMode": "priorityOnPrice",
                "extra": sell_quote.get("extra"),
            }
        )
        if not sell_result.get("success"):
            self._log(f"sell order rejected: {sell_result.get('message')}")
            return False

        realized = self.config.sell_target_amount
        profit_loss = realized - self.config.buy_amount

        trade = TradeRecord(
            time=time.time(),
            buy_amount=self.config.buy_amount,
            sell_amount=realized,
            profit_loss=profit_loss,
            cycle_number=next_cycle,
        )

        with self._lock:
            self.stats.trade_history.append(trade)
            self.stats.total_volume += self.config.buy_amount
            self.stats.total_profit += profit_loss
            self.stats.cycles_completed += 1
            self.stats.last_updated = time.time()

        self._log(
            "cycle %d complete: sold %.4f %s for P/L %.6f"
            % (
                trade.cycle_number,
                trade.sell_amount,
                self.config.from_token,
                trade.profit_loss,
            )
        )
        return True

    def start(self) -> None:
        if self._running:
            self._log("trading already running")
            return

        self._running = True
        self.stats.start_time = time.time()
        self._log("trading loop started")

        try:
            while self._running:
                if 0 < self.config.max_cycles <= self.stats.cycles_completed:
                    self._log("maximum configured cycles reached, stopping")
                    break

                success = self.run_cycle()
                if not success:
                    self._log("cycle failed; backing off before retry")
                    time.sleep(self.config.retry_delay_seconds)
                    continue

                time.sleep(self.config.cycle_interval_seconds)
        finally:
            self.stop()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._log("trading loop stopped")

    # ------------------------------------------------------------------
    def _log(self, message: str, *, level: int = logging.INFO) -> None:
        self.logs.append(message)
        self.logger.log(level, message)


def load_cookies(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read().strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Cookie JSON must be an object")
        return {str(k): str(v) for k, v in data.items()}
    # fallback: cookie header string
    result: Dict[str, str] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        result[name] = value
    return result


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
    if args.sell_amount is not None:
        data["sell_target_amount"] = args.sell_amount
    if args.cycles is not None:
        data["max_cycles"] = args.cycles
    if args.cycle_interval is not None:
        data["cycle_interval_seconds"] = args.cycle_interval
    if args.retry_delay is not None:
        data["retry_delay_seconds"] = args.retry_delay
    return TradeConfig(**data)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Binance Alpha backend trader")
    parser.add_argument(
        "--cookies",
        required=True,
        help="Path to file that stores Binance cookies (JSON map or raw Cookie header)",
    )
    parser.add_argument("--config", help="Path to config JSON file", default=None)
    parser.add_argument("--from-token", help="Token to swap from (default USDT)")
    parser.add_argument("--to-token", help="Token to swap to (default B2)")
    parser.add_argument("--contract-address", help="Destination token contract address")
    parser.add_argument("--buy-amount", type=float, help="Amount of from_token used per buy")
    parser.add_argument("--sell-amount", type=float, help="Target from_token amount when selling")
    parser.add_argument("--cycles", type=int, help="Maximum number of cycles to execute (0 for infinite)")
    parser.add_argument("--cycle-interval", type=float, help="Seconds to wait between successful cycles")
    parser.add_argument("--retry-delay", type=float, help="Seconds to wait after a failed cycle")
    parser.add_argument("--once", action="store_true", help="Run only a single cycle and exit")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    cookies = load_cookies(args.cookies)

    base_config = TradeConfig()
    if args.config:
        with open(args.config, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        base_config = TradeConfig(**data)

    config = build_config_from_args(base_config, args)

    service = BinanceTradingService(config=config, auth_cookies=cookies)

    def handle_signal(signum: int, frame: Optional[Any]) -> None:  # pylint: disable=unused-argument
        service._log(f"received signal {signum}; stopping", level=logging.INFO)
        service.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        service.run_cycle()
        service.stop()
    else:
        service.start()

    return 0


if __name__ == "__main__":
    sys.exit(main())
