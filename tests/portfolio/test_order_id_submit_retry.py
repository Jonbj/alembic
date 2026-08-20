"""Retry/backoff sul submit Alpaca (#203 §4, parte submit).

Il choke point e' `submit_order_with_coid_fallback`: dopo #313 tutti e sei i
siti submit ci passano, ed e' l'unico posto che conosce il `client_order_id`,
cioe' la chiave di idempotenza che rende sicuro un retry.

Lo spike di #201 (2026-08-20) ha misurato il rifiuto per duplicato come
HTTP 422 con codice Alpaca 40010001 "client_order_id must be unique" (NON 409).
Su un retry quel 422 significa "gia' inviato", non "fallito".
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError

from src.portfolio.order_id import submit_order_with_coid_fallback


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda _s: None)
    monkeypatch.setattr("src.util.retry.random.uniform", lambda _a, b: b)


def _api_error(status_code: int, body: str = "{}") -> APIError:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    response.text = body
    http_error = MagicMock()
    http_error.response = response
    return APIError(body, http_error)


_DUPLICATE_BODY = '{"code":40010001,"message":"client_order_id must be unique"}'


def _dedup_error() -> APIError:
    return _api_error(422, _DUPLICATE_BODY)


def _request(coid: str | None = "ambc-buy-AAPL-42"):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    return MarketOrderRequest(
        symbol="AAPL",
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=coid,
    )


# --- retry sul transiente ---------------------------------------------------

def test_transient_error_is_retried_with_the_same_client_order_id():
    trading_client = MagicMock()
    ok = MagicMock(id="order-1")
    trading_client.submit_order.side_effect = [_api_error(503), ok]

    result = submit_order_with_coid_fallback(trading_client, _request())

    assert result is ok
    assert trading_client.submit_order.call_count == 2
    first, second = trading_client.submit_order.call_args_list
    assert first.args[0].client_order_id == second.args[0].client_order_id == "ambc-buy-AAPL-42"


def test_submit_without_client_order_id_is_never_retried():
    """Senza chiave di idempotenza un retry puo' produrre due fill."""
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = _api_error(503)

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(trading_client, _request(None))

    trading_client.submit_order.assert_called_once()


def test_retries_exhausted_alerts_then_raises():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = _api_error(503)
    on_alert = MagicMock()

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(
            trading_client, _request(), on_alert=on_alert, max_attempts=3
        )

    assert trading_client.submit_order.call_count == 3
    on_alert.assert_called_once()
    assert "3" in on_alert.call_args.args[0]


# --- 422 dedup: "gia' inviato", non "fallito" -------------------------------

def test_duplicate_after_a_retry_resolves_to_the_existing_order():
    """503 poi 422/40010001: il primo submit era arrivato al broker."""
    trading_client = MagicMock()
    existing = MagicMock(id="order-already-there")
    trading_client.submit_order.side_effect = [_api_error(503), _dedup_error()]
    trading_client.get_order_by_client_id.return_value = existing
    on_alert = MagicMock()

    result = submit_order_with_coid_fallback(
        trading_client, _request(), on_alert=on_alert
    )

    assert result is existing
    trading_client.get_order_by_client_id.assert_called_once_with("ambc-buy-AAPL-42")
    assert trading_client.submit_order.call_count == 2
    on_alert.assert_called_once()


def test_duplicate_on_the_first_attempt_still_propagates():
    """Nessun retry nostro l'ha causato: e' un duplicato di un ciclo precedente."""
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = _dedup_error()

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(trading_client, _request())

    trading_client.submit_order.assert_called_once()
    trading_client.get_order_by_client_id.assert_not_called()


def test_duplicate_after_retry_reraises_when_lookup_finds_nothing():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = [_api_error(503), _dedup_error()]
    trading_client.get_order_by_client_id.return_value = None

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(trading_client, _request())


def test_duplicate_after_retry_reraises_when_lookup_itself_fails():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = [_api_error(503), _dedup_error()]
    trading_client.get_order_by_client_id.side_effect = _api_error(500)

    with pytest.raises(APIError) as excinfo:
        submit_order_with_coid_fallback(trading_client, _request())

    assert "40010001" in str(excinfo.value)


def test_duplicate_after_retry_is_not_retried_again():
    """Il ramo dedup risolve o rilancia: non consuma altri tentativi."""
    trading_client = MagicMock()
    existing = MagicMock(id="order-1")
    trading_client.submit_order.side_effect = [
        _api_error(503), _dedup_error(), MagicMock(id="MAI"),
    ]
    trading_client.get_order_by_client_id.return_value = existing

    assert submit_order_with_coid_fallback(trading_client, _request()) is existing
    assert trading_client.submit_order.call_count == 2


# --- 422 non-dedup: resta fail-fast ----------------------------------------

def test_non_duplicate_422_fails_fast_without_lookup():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = _api_error(
        422, '{"code":40310000,"message":"insufficient buying power"}'
    )
    on_alert = MagicMock()

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(trading_client, _request(), on_alert=on_alert)

    trading_client.submit_order.assert_called_once()
    trading_client.get_order_by_client_id.assert_not_called()
    on_alert.assert_not_called()


def test_lookup_is_skipped_when_the_client_cannot_do_it():
    trading_client = MagicMock(spec=["submit_order"])
    trading_client.submit_order.side_effect = [_api_error(503), _dedup_error()]

    with pytest.raises(APIError):
        submit_order_with_coid_fallback(trading_client, _request())
