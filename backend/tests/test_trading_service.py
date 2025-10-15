from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from trading_service import BinanceTradingService, TradeConfig


class DummyAsyncClient:
    """Minimal async client to capture requests sent by the service."""

    def __init__(self) -> None:
        self.cookies: Dict[str, str] = {"cr00": "dummy"}
        self.requests: list[Dict[str, Any]] = []
        self.timeout = 15
        self._closed = False

    async def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str]) -> Any:
        self.requests.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return DummyResponse({})

    async def get(self, url: str, headers: Dict[str, str]) -> Any:
        self.requests.append({"method": "GET", "url": url, "headers": headers})
        return DummyResponse({"data": []})

    async def aclose(self) -> None:
        self._closed = True


class DummyResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._json = payload

    def raise_for_status(self) -> None:  # pragma: no cover - dummy does nothing
        return None

    def json(self) -> Dict[str, Any]:
        return self._json


@pytest.fixture()
def service() -> BinanceTradingService:
    config = TradeConfig()
    client = DummyAsyncClient()

    svc = BinanceTradingService(
        config=config,
        auth_cookies={"cr00": "dummy"},
        extra_headers={},
        client=client,
    )
    svc._log = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    return svc


@pytest.mark.asyncio
async def test_get_quote(service: BinanceTradingService) -> None:
    async def fake_post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"data": {"foo": "bar"}}

    service._post = fake_post  # type: ignore
    quote = await service.get_quote({"a": 1}, label="test")
    assert quote == {"foo": "bar"}


@pytest.mark.asyncio
async def test_buy_token(service: BinanceTradingService) -> None:
    async def fake_post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": True, "traceId": "123"}

    service._post = fake_post  # type: ignore
    result = await service.buy_token({"amount": 1})
    assert result["success"] is True
    assert result["traceId"] == "123"


@pytest.mark.asyncio
async def test_get_usdt_balance(service: BinanceTradingService) -> None:
    async def fake_get(url: str) -> Dict[str, Any]:
        return {
            "data": [
                {
                    "accountType": "MAIN",
                    "assetBalances": [
                        {"asset": "USDT", "free": "123.456"}
                    ],
                }
            ]
        }

    service._get = fake_get  # type: ignore
    balance = await service.get_usdt_balance()
    assert balance == pytest.approx(123.456)


@pytest.mark.asyncio
async def test_get_asset_balance(service: BinanceTradingService) -> None:
    async def fake_get(url: str) -> Dict[str, Any]:
        return {
            "data": [
                {
                    "accountType": "SPOT",
                    "assetBalances": [
                        {"asset": "ABC", "free": "0.0"},
                    ],
                },
                {
                    "accountType": "CARD",
                    "assetBalances": [
                        {"asset": "KOGE", "free": "1.2345"},
                    ],
                },
            ]
        }

    service._get = fake_get  # type: ignore
    balance = await service.get_asset_balance("koge")
    assert balance == pytest.approx(1.2345)
