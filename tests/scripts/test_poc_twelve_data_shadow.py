"""Tests for the standalone PoC script (#458).

Copre:
- seam 2: dedup su external_id (lo script non riscrive righe gia' presenti).
- seam 3: isolamento dal path live (niente import di news_log / Redis store).
- edge case: ticker_valid, budget giornaliero, JSON malformato.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Caricamento lazy (lo script importa psycopg2 e src.connectors.*).
_SCRIPT = "scripts.poc_twelve_data_shadow"


@pytest.fixture
def script_module():
    return importlib.import_module(_SCRIPT)


@pytest.fixture
def fake_conn():
    """Mock della connessione psycopg2: tiene i cursori e simula il commit."""
    cursors = []
    cur = MagicMock()
    cur.fetchall.return_value = []
    cur.execute = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cursors.append(cur)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    conn.close = MagicMock()
    conn.autocommit = False
    return conn


def test_ticker_valid_match_case_insensitive(script_module):
    assert script_module._ticker_valid("AAPL reports Q4", "The AAPL stock rose", "AAPL") is True
    assert script_module._ticker_valid("aapl", "", "AAPL") is True
    # solo ticker parziale NON matcha (evita falsi positivi tipo AAPLX)
    assert script_module._ticker_valid("AAPLX rallies", "", "AAPL") is False
    assert script_module._ticker_valid("unrelated", "something else", "AAPL") is False


def test_existing_external_ids_dedup(script_module, fake_conn):
    cur = fake_conn.cursor()
    cur.fetchall.return_value = [("20260528C4858",), ("20260514GE59609",)]

    seen = script_module._existing_external_ids(cur, ["AAPL"])

    assert seen == {"20260528C4858", "20260514GE59609"}
    # la query filtra per poc_source corretto
    args, params = cur.execute.call_args.args
    assert "external_id" in args
    assert params[0] == "twelvedata_press_releases"
    assert params[1] == ["AAPL"]


# --- seam 2: dedup effettivo durante la fetch ---
@pytest.mark.asyncio
async def test_run_skips_already_seen_external_ids(script_module, fake_conn):
    """Se external_id e' gia' nel DB, lo script NON lo riscrive."""
    cur = fake_conn.cursor()
    cur.fetchall.return_value = [("X",)]  # un external_id gia' presente
    cur.fetchone.return_value = (0,)  # budget di oggi: 0 richieste

    # Connettore mock che produce UN item con id=td:X
    item = MagicMock()
    item.id = "td:X"
    item.title = "ok"
    item.body = "body"
    item.url = ""
    item.timestamp = None
    item.asset_tags = ["AAPL"]

    connector = MagicMock()
    connector.fetch_symbol = MagicMock(return_value=_aiter([item]))
    connector.last_response = {"press_releases": []}

    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL"])

    assert stats["fetched"] == 1
    assert stats["duplicates"] == 1
    assert stats["written"] == 0
    # l'INSERT non viene mai chiamato per il duplicato
    insert_calls = [
        c for c in cur.execute.call_args_list
        if c.args and "INSERT INTO news_poc_samples" in str(c.args[0])
    ]
    assert insert_calls == []


@pytest.mark.asyncio
async def test_run_writes_new_record_with_raw_response(script_module, fake_conn):
    cur = fake_conn.cursor()
    cur.fetchall.return_value = []  # nessun external_id gia' presente
    cur.fetchone.return_value = (0,)  # budget di oggi: 0 richieste

    import datetime as dt
    item = MagicMock()
    item.id = "td:NEWID"
    item.title = "AAPL fresh news"
    item.body = "fresh body"
    item.url = ""
    item.timestamp = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    item.asset_tags = ["AAPL"]

    connector = MagicMock()
    connector.fetch_symbol = MagicMock(return_value=_aiter([item]))
    connector.last_response = {
        "status": "ok",
        "press_releases": [
            {"id": "NEWID", "datetime": "2026-09-01T13:00:00Z",
             "title": "AAPL fresh news", "body": "<p>fresh body</p>"}
        ],
    }

    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL"])

    assert stats["fetched"] == 1
    assert stats["duplicates"] == 0
    assert stats["written"] == 1
    # una INSERT presente
    insert_calls = [
        c for c in cur.execute.call_args_list
        if c.args and "INSERT INTO news_poc_samples" in str(c.args[0])
    ]
    assert len(insert_calls) == 1
    args, params = insert_calls[0].args
    assert "INSERT INTO news_poc_samples" in args
    assert params[0] == "twelvedata_press_releases"
    assert params[1] == "AAPL"
    assert params[2] == "NEWID"
    # params[3]=title, [4]=body_chars, [5]=url, [6]=published_at,
    # [7]=latency_seconds, [8]=ticker_valid, [9]=raw_response
    assert params[8] is True
    # raw_response: la risposta GREZZA del fornitore, non un dict vuoto
    raw = json.loads(params[9])
    assert raw["id"] == "NEWID"
    assert raw["body"] == "<p>fresh body</p>"


# --- edge case 8: budget giornaliero esplicito, fermato da noi ---
@pytest.mark.asyncio
async def test_run_stops_when_daily_budget_exhausted(script_module, fake_conn):
    """Il contatore giornaliero deve fermare lo script: se il budget e' gia'
    stato consumato, nessuna nuova chiamata API parte."""
    cur = fake_conn.cursor()
    cur.fetchone.return_value = (script_module._DAILY_REQUEST_BUDGET,)  # budget raggiunto

    connector = MagicMock()
    connector.fetch_symbol = MagicMock()

    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL", "MSFT"])

    assert stats["requested"] == 0
    assert stats["written"] == 0
    connector.fetch_symbol.assert_not_called()
    # il budget e' stato CONSULTATO (ledger), non ignorato
    ledger_reads = [
        c for c in cur.execute.call_args_list
        if c.args and "news_poc_request_budget" in str(c.args[0])
    ]
    assert len(ledger_reads) >= 1


@pytest.mark.asyncio
async def test_run_records_each_request_in_the_budget_ledger(script_module, fake_conn):
    """Ogni chiamata API consuma un credito del ledger giornaliero."""
    cur = fake_conn.cursor()
    cur.fetchall.return_value = []
    cur.fetchone.return_value = (0,)

    import datetime as dt
    item = MagicMock()
    item.id = "td:A"
    item.title = "t"
    item.body = "b"
    item.url = ""
    item.timestamp = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    item.asset_tags = ["AAPL"]

    connector = MagicMock()
    connector.fetch_symbol = MagicMock(return_value=_aiter([item]))
    connector.last_response = {"press_releases": []}

    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL", "MSFT"])

    ledger_calls = [
        c for c in cur.execute.call_args_list
        if c.args and "INSERT INTO news_poc_request_budget" in str(c.args[0])
    ]
    # una scrittura nel ledger per simbolo chiamato (2 simboli, budget non raggiunto)
    assert len(ledger_calls) == 2
    assert stats["requested"] == 2


@pytest.mark.asyncio
async def test_run_stops_mid_coorte_when_budget_runs_out(script_module, fake_conn):
    """Il budget fermia lo script a meta' coorte: i simboli restanti non vengono
    chiamati oltre il piano."""
    cur = fake_conn.cursor()
    cur.fetchall.return_value = []
    cur.fetchone.side_effect = [(0,), (1,), (1,)]  # dopo la prima richiesta il cap e' raggiunto

    connector = MagicMock()
    connector.fetch_symbol = MagicMock(return_value=_aiter([]))
    connector.last_response = {"press_releases": []}

    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector), \
         patch.object(script_module, "_DAILY_REQUEST_BUDGET", 1):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL", "MSFT", "GOOGL"])

    assert stats["requested"] == 1
    assert connector.fetch_symbol.call_count == 1


# --- edge case 1: rate limit — backoff, il simbolo non blocca gli altri ---
@pytest.mark.asyncio
async def test_run_rate_limited_symbol_does_not_block_the_others(script_module, fake_conn):
    """Un simbolo rate-limited viene saltato (backoff) e riprovato a fine giro;
    gli altri simboli della coorte vengono comunque processati."""
    from src.connectors.twelve_data_press_releases import TwelveDataRateLimitError

    cur = fake_conn.cursor()
    cur.fetchall.return_value = []
    cur.fetchone.return_value = (0,)

    import datetime as dt
    item = MagicMock()
    item.id = "td:MSFT1"
    item.title = "MSFT news"
    item.body = "body"
    item.url = ""
    item.timestamp = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    item.asset_tags = ["MSFT"]

    connector = MagicMock()
    # AAPL sballa il rate limit, MSFT risponde regolarmente; al retry di fine
    # giro AAPL risponde vuoto (niente di nuovo dal fornitore)
    connector.fetch_symbol = MagicMock(side_effect=[
        TwelveDataRateLimitError("429 — credit/min exhausted"),
        _aiter([item]),
        _aiter([]),
    ])
    connector.last_response = {"press_releases": []}

    sleep_mock = AsyncMock()
    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector), \
         patch.object(script_module, "_RATE_LIMIT_BACKOFF_S", 0), \
         patch.object(script_module.asyncio, "sleep", sleep_mock):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL", "MSFT"])

    assert stats["written"] == 1
    assert stats["rate_limited"] == 1
    # il backoff e' avvenuto prima di riprovare il simbolo rinviato
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_gives_up_after_max_rate_limit_retries(script_module, fake_conn):
    """Dopo _MAX_RATE_LIMIT_RETRIES giri di backoff il simbolo e' abbandonato:
    lo script termina, non loopa all'infinito sul rate limit."""
    from src.connectors.twelve_data_press_releases import TwelveDataRateLimitError

    cur = fake_conn.cursor()
    cur.fetchall.return_value = []
    cur.fetchone.return_value = (0,)

    connector = MagicMock()
    connector.fetch_symbol = MagicMock(
        side_effect=TwelveDataRateLimitError("429 — credit/min exhausted")
    )

    sleep_mock = AsyncMock()
    with patch.object(script_module, "_conn", return_value=fake_conn), \
         patch.object(script_module, "TwelveDataPressReleasesConnector", return_value=connector), \
         patch.object(script_module, "_RATE_LIMIT_BACKOFF_S", 0), \
         patch.object(script_module.asyncio, "sleep", sleep_mock):
        with patch.dict("os.environ", {"TWELVE_DATA_API_KEY": "k"}):
            stats = await script_module._run(["AAPL"])

    # il primo tentativo piu' _MAX_RATE_LIMIT_RETRIES giri di backoff, poi stop
    assert stats["rate_limited"] == 1 + script_module._MAX_RATE_LIMIT_RETRIES
    assert stats["written"] == 0
    assert sleep_mock.await_count == script_module._MAX_RATE_LIMIT_RETRIES


def test_isolation_from_live_path(script_module):
    """seam 3: lo script non importa moduli del path live.

    Protezione da futuri refactor che accidentalmente ricolleghino la PoC al
    path live (es. aggiungendo `from src.store import redis_store`).
    """
    forbidden = (
        "src.store.redis_store",
        "src.workers.news_log",
        "src.workers.sentiment",
        "src.workers.queue",
    )
    script_path = script_module.__file__
    src = open(script_path).read()
    for bad in forbidden:
        assert bad not in src, (
            f"seam 3 violated: {script_path} importa {bad}"
        )


def test_isolation_imports_submodules(script_module):
    """Controllo simbolico extra: gli import di alto livello dello script."""
    # lo script importa il connettore (atteso) e psycopg2 (atteso).
    import inspect
    source = inspect.getsource(script_module)
    assert "src.connectors.twelve_data_press_releases" in source
    assert "psycopg2" in source


def test_daily_budget_cap_is_set_below_plan_basic_limit(script_module):
    """Edge case 8: budget giornaliero esplicito sotto le 800 del piano Basic."""
    assert script_module._DAILY_REQUEST_BUDGET < 800
    assert script_module._DAILY_REQUEST_BUDGET >= 640  # coorte 20 * 4 * 8 = 640


async def _aiter(items):
    for x in items:
        yield x