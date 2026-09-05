#!/usr/bin/env python3
"""Misura «emittente autore della previsione, non suo oggetto» (issue #492).

Lo script e' sola lettura su PostgreSQL, Redis e Alpaca. Non modifica prompt,
segnali, soglie o decisioni live: durante il freeze #171 produce esclusivamente
evidenza. Cerca nella watchlist titoli in cui un alias dell'emittente e'
soggetto di un verbo di previsione/giudizio e il contenuto riguarda un oggetto
esterno. Include sia la forma diretta (``Goldman warns investors ...``) sia
l'attribuzione in coda (``Markets may fall, Morgan Stanley says``).

Output:
    docs/evidence/issuer_as_author_492.json
    docs/evidence/issuer_as_author_492.md

Uso:
    python scripts/measure_issuer_as_author.py
    python scripts/measure_issuer_as_author.py --candidates-only
    python scripts/measure_issuer_as_author.py --skip-alpaca
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from bisect import bisect_left
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
# Il comando documentato e' `python scripts/...`: in quel caso Python mette
# `scripts/`, non la root del repository, in testa al path.
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
OUT_JSON = PROJECT_DIR / "docs" / "evidence" / "issuer_as_author_492.json"
OUT_MD = PROJECT_DIR / "docs" / "evidence" / "issuer_as_author_492.md"
TRADING_YAML = PROJECT_DIR / "config" / "trading.yaml"

DEFAULT_SINCE = date(2026, 7, 1)
VARIANTE_A_SINCE = datetime(2026, 9, 1, tzinfo=UTC)
REVERSAL_THRESHOLD = -0.35
DEFAULT_ENTRY_THRESHOLD = 0.30
MIN_MANUAL_SAMPLE = 20

# Questi sono pattern di misura, non parametri della strategia.
VERBS = (
    "warns",
    "sees",
    "expects",
    "forecasts",
    "predicts",
    "says",
    "downgrades",
    "upgrades",
    "raises",
    "cuts",
    "initiates",
    "reiterates",
    "names",
    "adds",
)
_VERB_PATTERN = "|".join(re.escape(v) for v in VERBS)
_ACTOR_QUALIFIERS = (
    r"(?:chief|top|global|senior|lead|equity|market|macro|tech|research|investment|"
    r"executive|ceo|cfo|cio|economist|analyst|strategist|specialist|team|arm|group|"
    r"bank|report|desk|head|veteran|researchers?|analysts?|strategists?)"
)
_BETWEEN_ALIAS_AND_VERB = rf"(?:\s+{_ACTOR_QUALIFIERS}){{0,7}}\s*[,;:\-–—]*\s*"

# Complementi che rendono esplicito che l'emittente parla di se'. Evitiamo
# liste semantiche aggressive: i casi ambigui restano candidati e vengono
# giudicati nel campione manuale, anziche' sparire dal denominatore.
_SELF_COMPLEMENT = re.compile(
    r"\b(?:itself|its\s+(?:(?:own|quarterly|annual|full[- ]year)\s+)?"
    r"(?:earnings|revenue|sales|guidance|outlook|dividend|profit|profits|margin|"
    r"margins|shares|stock|demand|production|results|forecast))\b",
    re.IGNORECASE,
)

# La validazione e' deliberatamente dati-specifica e vive vicino alla misura:
# ogni label e nota viene anche copiata integralmente negli output. Viene
# popolata dopo `--candidates-only`; `main` rifiuta un report con meno di 20.
MANUAL_LABELS: dict[int, dict[str, object]] = {
    1887: {"classe": True, "nota": "view su rotazione AI, attribuzione in coda"},
    1916: {"classe": True, "nota": "Deutsche Bank valuta Qnity"},
    2096: {"classe": True, "nota": "responsabile macro parla di AI e lavoro"},
    2121: {"classe": True, "nota": "warning su downgrade di Travis Perkins"},
    2284: {"classe": True, "nota": "view sull'opportunita' nei private markets"},
    2609: {"classe": False, "nota": "CEO AMAT parla della domanda per AMAT"},
    2660: {"classe": True, "nota": "price target su Lam Research"},
    2664: {"classe": True, "nota": "price target su KLA"},
    2712: {"classe": False, "nota": "duplicato: CEO AMAT parla della propria domanda"},
    2872: {"classe": True, "nota": "analista Morgan Stanley valuta Watsco"},
    3076: {"classe": True, "nota": "Goldman raccomanda NIO"},
    3476: {"classe": False, "nota": "Ericsson e' oggetto del volume opzioni"},
    3499: {"classe": True, "nota": "price target su Alnylam"},
    3566: {"classe": False, "nota": "costi componenti impattano i risultati Ericsson"},
    3591: {"classe": True, "nota": "price target su AMD"},
    3677: {"classe": True, "nota": "Morgan Stanley raccomanda CAVA"},
    3715: {"classe": True, "nota": "Morgan Stanley valuta Nvidia"},
    3822: {"classe": False, "nota": "GE descrive il proprio vincolo di crescita"},
    3927: {"classe": False, "nota": "TSMC annuncia il proprio capex"},
    4773: {"classe": False, "nota": "Lilly comunica risultati del proprio farmaco"},
    4782: {"classe": True, "nota": "view Morgan Stanley sui tassi Fed"},
    5250: {"classe": True, "nota": "Deutsche Bank valuta il volo Starship"},
    5922: {"classe": False, "nota": "Novo comunica esito del proprio trial"},
    6228: {"classe": True, "nota": "view sulla spesa cloud aggregata"},
    6290: {"classe": True, "nota": "Palantir formula un warning sulle aziende clienti"},
    6461: {"classe": False, "nota": "Novo alza la propria guidance"},
    6486: {"classe": False, "nota": "Caterpillar alza il proprio forecast vendite"},
    6569: {"classe": False, "nota": "Disney quantifica il proprio rimborso"},
    7093: {"classe": False, "nota": "TSMC e' oggetto del salto delle proprie vendite"},
    7247: {"classe": True, "nota": "Morgan Stanley valuta SpaceX"},
    7492: {"classe": True, "nota": "CEO Novo parla dei costi sanitari USA"},
    7702: {"classe": False, "nota": "JD descrive il proprio profitto"},
    7858: {"classe": True, "nota": "analista Morgan Stanley valuta Klarna"},
    7948: {"classe": True, "nota": "Morgan Stanley valuta Reliance"},
    8182: {"classe": True, "nota": "analista Morgan Stanley valuta ONEOK"},
    8484: {"classe": True, "nota": "Morgan Stanley declassa Baidu"},
    8540: {"classe": False, "nota": "AMAT prevede la propria crescita"},
    8790: {"classe": False, "nota": "Alibaba annuncia la propria raccolta"},
    8899: {
        "classe": True,
        "nota": "raccomandazione su altro titolo, attribuzione in coda",
    },
    9016: {"classe": True, "nota": "Morgan Stanley valuta SpaceX"},
    9053: {"classe": True, "nota": "Morgan Stanley valuta SpaceX"},
    9088: {"classe": True, "nota": "Morgan Stanley valuta Williams-Sonoma"},
    9099: {"classe": True, "nota": "Goldman valuta Salesforce"},
    9134: {"classe": False, "nota": "AMAT descrive la propria crescita"},
    9141: {"classe": True, "nota": "Morgan Stanley alza target Salesforce"},
    9401: {"classe": True, "nota": "Deutsche Bank nomina titoli hardware AI"},
    9412: {"classe": True, "nota": "CEO Goldman formula una view macro sugli USA"},
    9478: {"classe": True, "nota": "Morgan Stanley promuove HOOD"},
    9484: {"classe": True, "nota": "Deutsche Bank nomina Lumentum e Coherent"},
    9529: {"classe": True, "nota": "Morgan Stanley valuta Meta"},
    9538: {"classe": True, "nota": "Deutsche Bank valuta SiriusXM"},
    9593: {
        "classe": True,
        "nota": "Goldman avverte gli investitori sui rendimenti di mercato",
    },
    9660: {"classe": True, "nota": "analista Morgan Stanley valuta MiniMed"},
    9676: {
        "classe": True,
        "nota": "Morgan Stanley formula una view sulle banche asiatiche",
    },
}


QUERY_SIGNALS = """\
SELECT row_to_json(q)::text
FROM (
    SELECT s.id AS signal_id, s.symbol, s.generated_at, s.score, s.confidence,
           s.model_id, s.ensemble_std, s.reasoning, s.news_log_id,
           n.title, n.url, n.source, n.published_at
    FROM sentiment_signals s
    JOIN news_log n ON n.id = s.news_log_id
    WHERE s.generated_at >= '{since}'
      AND s.generated_at < '{until}'
    ORDER BY s.generated_at, s.id
) q;"""

QUERY_ALIASES = """\
SELECT row_to_json(q)::text
FROM (
    SELECT ticker, company_name, aliases
    FROM ticker_lookup
    ORDER BY ticker, company_name
) q;"""

QUERY_DECISIONS = """\
SELECT row_to_json(q)::text
FROM (
    SELECT id, signal_id, tick_time, symbol, decision, order_id, signal_score, reason
    FROM execution_decisions
    WHERE signal_id IS NOT NULL
      AND decision IN ('BUY', 'SELL')
      AND tick_time >= '{since}'
      AND tick_time < '{until}'
    ORDER BY tick_time, id
) q;"""

QUERY_TRADES = """\
SELECT row_to_json(q)::text
FROM (
    SELECT id, signal_id, decision_id, symbol, entry_notional, entry_price,
           entry_time,
           CASE WHEN exit_time < '{until}' THEN exit_order_id END AS exit_order_id,
           CASE WHEN exit_time < '{until}' THEN exit_order_ids ELSE ARRAY[]::text[] END AS exit_order_ids,
           CASE WHEN exit_time < '{until}' THEN exit_price END AS exit_price,
           CASE WHEN exit_time < '{until}' THEN exit_time END AS exit_time,
           qty,
           CASE WHEN exit_time < '{until}' THEN net_pnl END AS net_pnl,
           CASE WHEN exit_time < '{until}' THEN exit_reason END AS exit_reason
    FROM trades
    WHERE entry_time < '{until}'
      AND (entry_time >= '{since}' OR exit_time >= '{since}')
    ORDER BY id
) q;"""


def _psql_json(sql: str) -> list[dict]:
    """Esegue una SELECT read-only via il container e legge una riga JSON per record."""
    command = [
        "docker",
        "exec",
        "alembic-postgres-1",
        "psql",
        "-U",
        "trading",
        "-d",
        "trading",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Query fallita: {result.stderr.strip()[:400]}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _watchlist() -> set[str]:
    cfg = yaml.safe_load(TRADING_YAML.read_text())
    return {
        str(symbol).upper() for symbol in cfg.get("symbols", {}).get("watchlist", [])
    }


def leggi_alias(watchlist: set[str]) -> dict[str, list[str]]:
    """Alias DB per tutta la watchlist; niente ticker corti usati come parole comuni."""
    result: dict[str, set[str]] = {symbol: set() for symbol in watchlist}
    for row in _psql_json(QUERY_ALIASES):
        symbol = str(row["ticker"]).upper()
        if symbol not in result:
            continue
        values = [row.get("company_name"), *(row.get("aliases") or [])]
        for value in values:
            if value and _alias_sicuro(str(value), symbol):
                result[symbol].add(str(value).strip())
    return {
        symbol: sorted(values, key=lambda value: (-len(value), value.lower()))
        for symbol, values in result.items()
    }


def _alias_sicuro(alias: str, symbol: str) -> bool:
    alias = alias.strip()
    if len(alias) < 4:
        return False
    # Anche ticker lunghi come AMAT non sono nomi societari: la ricerca e' sul
    # nome/alias dell'emittente, non sulla presenza di un cashtag.
    return alias.casefold() != symbol.casefold()


def _normalizza(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value.replace("’", "'").replace("`", "'")).strip()


def _alias_pattern(alias: str) -> str:
    # Spazi e punteggiatura societaria tolleranti, ma confini lessicali netti.
    pieces = re.split(r"\s+", _normalizza(alias))
    body = r"\s+".join(re.escape(piece) for piece in pieces)
    return rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"


def _complemento_parla_dell_emittente(complemento: str, aliases: Iterable[str]) -> bool:
    if _SELF_COMPLEMENT.search(complemento):
        return True
    for alias in aliases:
        if not _alias_sicuro(alias, ""):
            continue
        if re.search(_alias_pattern(alias), complemento, re.IGNORECASE):
            return True
    return False


def classifica_titolo(title: str, symbol: str, aliases: Iterable[str]) -> dict | None:
    """Restituisce il match euristico, oppure ``None``.

    La funzione produce soltanto candidati. La verita' di classe viene dalla
    revisione manuale campionata, riportata separatamente come precisione.
    """
    normalized = _normalizza(title)
    safe_aliases = [a for a in aliases if _alias_sicuro(a, symbol)]
    for alias in sorted(set(safe_aliases), key=len, reverse=True):
        pattern = re.compile(
            rf"(?P<alias>{_alias_pattern(alias)})(?P<qualificatori>{_BETWEEN_ALIAS_AND_VERB})"
            rf"(?P<verbo>{_VERB_PATTERN})\b(?P<dopo>.*)$",
            re.IGNORECASE,
        )
        for match in pattern.finditer(normalized):
            before = normalized[: match.start()].strip(" ,;:-–—")
            after = match.group("dopo").strip(" ,;:-–—")
            # Con attributo in coda (`claim, Morgan Stanley says`) la tesi e'
            # prima dell'alias. Negli altri casi e' il complemento del verbo.
            trailing_attribution = not after and bool(before)
            complement = before if trailing_attribution else after
            if len(complement) < 3:
                continue
            if _complemento_parla_dell_emittente(complement, safe_aliases):
                continue
            return {
                "alias": match.group("alias"),
                "verbo": match.group("verbo"),
                "complemento": complement,
                "forma": "attribuzione_in_coda"
                if trailing_attribution
                else "soggetto_diretto",
            }
    return None


def supera_soglia_operativa(score: float, entry_threshold: float) -> str | None:
    if score <= REVERSAL_THRESHOLD:
        return "reversal"
    if score >= entry_threshold:
        return "long_entry"
    return None


def _read_entry_threshold() -> tuple[float, str]:
    """Legge il gate vivo senza scriverlo; fallback al baseline documentato."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            "alembic-redis-1",
            "redis-cli",
            "--raw",
            "MGET",
            "feedback:entry_threshold:S4",
            "feedback:entry_threshold",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        values = [line.strip() for line in result.stdout.splitlines()]
        for key, value in zip(
            ("feedback:entry_threshold:S4", "feedback:entry_threshold"), values
        ):
            if value:
                try:
                    return float(value), f"redis:{key}"
                except ValueError:
                    pass
    return DEFAULT_ENTRY_THRESHOLD, "config:loss_feedback.threshold_baseline"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _trade_matches_decision(trade: dict, decision: dict) -> bool:
    if decision["decision"] == "BUY":
        return (
            trade.get("decision_id") == decision["id"]
            or trade.get("signal_id") == decision["signal_id"]
        )
    order_id = decision.get("order_id")
    if not order_id:
        return False
    return trade.get("exit_order_id") == order_id or order_id in (
        trade.get("exit_order_ids") or []
    )


def _notional_for_trade(trade: dict, decisions: list[dict]) -> float | None:
    if any(d["decision"] == "SELL" for d in decisions):
        price, qty = trade.get("exit_price"), trade.get("qty")
        if price is not None and qty is not None:
            return abs(float(price) * float(qty))
    value = trade.get("entry_notional")
    return abs(float(value)) if value is not None else None


def calcola_impatto(
    candidates: list[dict], decisions: list[dict], trades: list[dict]
) -> tuple[list[dict], dict]:
    """Collega decisioni BUY/SELL via FK e trade via entry/exit order id.

    Nessun join per prossimita' di score/orario: sarebbe comodo ma attribuirebbe
    al candidato righe non dimostrabili. Lo stesso trade e' deduplicato sia per
    candidato sia nella sintesi globale.
    """
    decisions_by_signal: dict[int, list[dict]] = {}
    for decision in decisions:
        signal_id = decision.get("signal_id")
        if signal_id is not None and decision.get("decision") in {"BUY", "SELL"}:
            decisions_by_signal.setdefault(int(signal_id), []).append(decision)

    enriched: list[dict] = []
    all_decisions: dict[int, dict] = {}
    all_trades: dict[int, tuple[dict, list[dict]]] = {}
    candidates_with_decision = 0
    for candidate in candidates:
        signal_id = int(candidate["signal_id"])
        linked_decisions = decisions_by_signal.get(signal_id, [])
        if linked_decisions:
            candidates_with_decision += 1
        linked_trades = {
            int(trade["id"]): trade
            for trade in trades
            if any(
                _trade_matches_decision(trade, decision)
                for decision in linked_decisions
            )
        }
        for decision in linked_decisions:
            all_decisions[int(decision["id"])] = decision
        for trade_id, trade in linked_trades.items():
            matching = [
                d for d in linked_decisions if _trade_matches_decision(trade, d)
            ]
            all_trades.setdefault(trade_id, (trade, matching))

        pnl = sum(
            float(t["net_pnl"])
            for t in linked_trades.values()
            if t.get("exit_time") and t.get("net_pnl") is not None
        )
        enriched.append(
            {
                **candidate,
                "decisioni": linked_decisions,
                "trade_ids": sorted(linked_trades),
                "pnl_realizzato_usd": pnl,
            }
        )

    notionals = [
        _notional_for_trade(trade, linked_decisions)
        for trade, linked_decisions in all_trades.values()
    ]
    summary = {
        "candidati_con_decisione_buy_sell": candidates_with_decision,
        "decisioni_buy_sell": len(all_decisions),
        "trade_collegati": len(all_trades),
        "notional_mosso_usd": sum(value for value in notionals if value is not None),
        "pnl_realizzato_usd": sum(
            float(trade["net_pnl"])
            for trade, _ in all_trades.values()
            if trade.get("exit_time") and trade.get("net_pnl") is not None
        ),
    }
    return enriched, summary


def controfattuali_una_seduta(
    candidates: list[dict], closes: dict[str, list[tuple[date, float]]]
) -> dict[int, dict]:
    """Close-to-close dalla prima seduta >= giorno segnale alla successiva."""
    result: dict[int, dict] = {}
    for candidate in candidates:
        signal_id = int(candidate["signal_id"])
        generated_day = _dt(candidate["generated_at"]).date()
        bars = sorted(closes.get(candidate["symbol"], []))
        days = [day for day, _ in bars]
        index = bisect_left(days, generated_day)
        if index + 1 >= len(bars):
            result[signal_id] = {
                "seduta_base": None,
                "seduta_successiva": None,
                "close_base": None,
                "close_successivo": None,
                "rendimento_1_seduta": None,
            }
            continue
        base_day, base_close = bars[index]
        next_day, next_close = bars[index + 1]
        result[signal_id] = {
            "seduta_base": base_day.isoformat(),
            "seduta_successiva": next_day.isoformat(),
            "close_base": base_close,
            "close_successivo": next_close,
            "rendimento_1_seduta": next_close / base_close - 1 if base_close else None,
        }
    return result


def fetch_closes_alpaca(candidates: list[dict], until: date) -> tuple[dict, str]:
    """Barre daily Alpaca in batch, corporate actions incluse (`adjustment=all`)."""
    if not candidates:
        return {}, "nessun_candidato"
    try:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        from src.config import config
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - dipendenze ambiente
        return {}, f"non_disponibile:{type(exc).__name__}"

    start = min(_dt(row["generated_at"]).date() for row in candidates)
    symbols = sorted({row["symbol"] for row in candidates})
    key = config.ALPACA_API_KEY or os.environ.get("ALPACA_API_KEY", "")
    secret = config.ALPACA_SECRET_KEY or os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        # Nei worktree autonomi il file .env non viene copiato, mentre il
        # worker gia' in esecuzione ha credenziali e SDK. Il fallback resta
        # una sola lettura di barre e non stampa mai i segreti.
        return _fetch_closes_alpaca_worker(symbols, start, until)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
        end=datetime.combine(
            until + timedelta(days=8), datetime.min.time(), tzinfo=UTC
        ),
        feed=DataFeed.IEX,
        adjustment=Adjustment.ALL,
    )
    try:
        barset = StockHistoricalDataClient(key, secret).get_stock_bars(request)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - rete/provider
        return _fetch_closes_alpaca_worker(
            symbols, start, until, errore_host=type(exc).__name__
        )
    closes: dict[str, list[tuple[date, float]]] = {}
    for symbol, bars in barset.data.items():
        closes[symbol] = [(bar.timestamp.date(), float(bar.close)) for bar in bars]
    return closes, "Alpaca IEX daily adjustment=all"


def _fetch_closes_alpaca_worker(
    symbols: list[str], start: date, until: date, errore_host: str | None = None
) -> tuple[dict[str, list[tuple[date, float]]], str]:
    """Fallback read-only nel worker, che possiede credenziali e SDK Alpaca."""
    spec = json.dumps(
        {
            "symbols": symbols,
            "start": start.isoformat(),
            "end": (until + timedelta(days=8)).isoformat(),
        }
    )
    code = """
import json, os, sys
from datetime import datetime, timezone
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
spec = json.loads(sys.argv[1])
client = StockHistoricalDataClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET_KEY'])
request = StockBarsRequest(
    symbol_or_symbols=spec['symbols'], timeframe=TimeFrame.Day,
    start=datetime.fromisoformat(spec['start']).replace(tzinfo=timezone.utc),
    end=datetime.fromisoformat(spec['end']).replace(tzinfo=timezone.utc),
    feed=DataFeed.IEX, adjustment=Adjustment.ALL,
)
bars = client.get_stock_bars(request).data
print(json.dumps({symbol: [[bar.timestamp.date().isoformat(), float(bar.close)] for bar in rows]
                  for symbol, rows in bars.items()}))
"""
    result = subprocess.run(
        ["docker", "exec", "alembic-worker-1", "python", "-c", code, spec],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        reason = "worker_non_disponibile"
        if errore_host:
            reason += f"_dopo_{errore_host}"
        return {}, reason
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}, "risposta_worker_non_valida"
    closes = {
        symbol: [(date.fromisoformat(day), float(close)) for day, close in rows]
        for symbol, rows in raw.items()
    }
    return closes, "Alpaca IEX daily adjustment=all (via worker)"


def stato_validazione_manuale(
    candidates: list[dict],
    labels: dict[int, dict[str, object]],
    minimum: int = MIN_MANUAL_SAMPLE,
) -> dict:
    candidate_ids = {int(row["signal_id"]) for row in candidates}
    selected = [
        (int(signal_id), label)
        for signal_id, label in labels.items()
        if int(signal_id) in candidate_ids
    ]
    if len(selected) < minimum:
        raise ValueError(
            f"validazione manuale incompleta: {len(selected)} candidati, ne servono almeno {minimum}"
        )
    positives = sum(bool(label["classe"]) for _, label in selected)
    rows = [
        {
            "signal_id": signal_id,
            "classe": bool(label["classe"]),
            "nota": str(label.get("nota", "")),
        }
        for signal_id, label in sorted(selected)
    ]
    return {
        "n_classificati": len(selected),
        "classe": positives,
        "non_classe": len(selected) - positives,
        "precisione_euristica": positives / len(selected),
        "campione": rows,
    }


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _candidates(
    signals: list[dict], aliases: dict[str, list[str]], entry_threshold: float
) -> list[dict]:
    result = []
    for signal in signals:
        symbol = str(signal["symbol"]).upper()
        match = classifica_titolo(
            signal.get("title") or "", symbol, aliases.get(symbol, [])
        )
        if match is None:
            continue
        generated = _dt(signal["generated_at"])
        result.append(
            {
                **signal,
                "symbol": symbol,
                "score": float(signal["score"]),
                "confidence": float(signal["confidence"]),
                "ensemble_std": (
                    float(signal["ensemble_std"])
                    if signal.get("ensemble_std") is not None
                    else None
                ),
                "match_heuristico": match,
                "soglia_operativa_superata": supera_soglia_operativa(
                    float(signal["score"]), entry_threshold
                ),
                "segmento_prompt": (
                    "variante_a" if generated >= VARIANTE_A_SINCE else "pre_variante_a"
                ),
            }
        )
    return result


def riepilogo_segmenti_prompt(
    candidates: list[dict], decisions: list[dict], trades: list[dict]
) -> dict[str, dict]:
    """Separa esplicitamente il campione prima/dopo Variante A (#399/#408)."""
    result = {}
    for segment in ("pre_variante_a", "variante_a"):
        rows = [row for row in candidates if row["segmento_prompt"] == segment]
        confirmed = [
            row for row in rows if row.get("classe_validata_manualmente") is True
        ]
        _, impact = calcola_impatto(rows, decisions, trades)
        _, confirmed_impact = calcola_impatto(confirmed, decisions, trades)
        result[segment] = {
            "candidati": len(rows),
            "candidati_sopra_soglia": sum(
                row["soglia_operativa_superata"] is not None for row in rows
            ),
            **impact,
            "classe_validata": {
                "candidati": len(confirmed),
                "candidati_sopra_soglia": sum(
                    row["soglia_operativa_superata"] is not None for row in confirmed
                ),
                **confirmed_impact,
            },
        }
    return result


def misura(
    since: date,
    until: date,
    *,
    skip_alpaca: bool = False,
    manual_labels: dict[int, dict[str, object]] | None = None,
) -> dict:
    watchlist = _watchlist()
    aliases = leggi_alias(watchlist)
    entry_threshold, threshold_source = _read_entry_threshold()
    bounds = {
        "since": datetime.combine(since, datetime.min.time(), tzinfo=UTC).isoformat(),
        "until": datetime.combine(
            until + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        ).isoformat(),
    }
    signals = _psql_json(QUERY_SIGNALS.format(**bounds))
    signals = [row for row in signals if str(row["symbol"]).upper() in watchlist]
    candidates = _candidates(signals, aliases, entry_threshold)

    decisions = _psql_json(QUERY_DECISIONS.format(**bounds))
    trades = _psql_json(QUERY_TRADES.format(**bounds))
    candidates, impact = calcola_impatto(candidates, decisions, trades)

    closes: dict[str, list[tuple[date, float]]]
    if skip_alpaca:
        closes, price_source = {}, "saltato_da_cli"
    else:
        closes, price_source = fetch_closes_alpaca(candidates, until)
    counterfactuals = controfattuali_una_seduta(candidates, closes)
    for candidate in candidates:
        candidate["controfattuale_1_seduta"] = counterfactuals[
            int(candidate["signal_id"])
        ]

    validation = stato_validazione_manuale(
        candidates, MANUAL_LABELS if manual_labels is None else manual_labels
    )
    manual_by_id = {row["signal_id"]: row["classe"] for row in validation["campione"]}
    for candidate in candidates:
        candidate["classe_validata_manualmente"] = manual_by_id.get(
            int(candidate["signal_id"])
        )
    confirmed = [
        row for row in candidates if row["classe_validata_manualmente"] is True
    ]
    _, confirmed_impact = calcola_impatto(confirmed, decisions, trades)
    segments = riepilogo_segmenti_prompt(candidates, decisions, trades)
    n_above = sum(row["soglia_operativa_superata"] is not None for row in candidates)
    confirmed_above = sum(
        row["soglia_operativa_superata"] is not None for row in confirmed
    )
    cf_available = sum(
        row["controfattuale_1_seduta"]["rendimento_1_seduta"] is not None
        for row in candidates
    )
    return {
        "issue": 492,
        "generato_il": datetime.now(UTC).isoformat(),
        "finestra": {"dal": since.isoformat(), "al_incluso": until.isoformat()},
        "metodo": {
            "universo": "config/trading.yaml symbols.watchlist",
            "pattern_verbi": list(VERBS),
            "attribuzione_decisioni": "solo execution_decisions.signal_id diretto",
            "attribuzione_trade": "BUY via decision_id/signal_id; SELL via exit_order_id",
            "reversal_threshold": REVERSAL_THRESHOLD,
            "entry_threshold": entry_threshold,
            "entry_threshold_source": threshold_source,
            "entry_threshold_temporalita": (
                "snapshot al momento del run; Redis non conserva la serie storica del gate"
            ),
            "fonte_prezzi": price_source,
            "proposta_non_applicata": (
                "Nel prompt distinguere esplicitamente l'azienda fonte dell'affermazione "
                "dall'azienda oggetto: se l'emittente pubblica una view su mercato, investitori "
                "o un altro titolo, non trattarla come guidance sui propri fondamentali."
            ),
        },
        "riepilogo": {
            "segnali_esaminati": len(signals),
            "candidati": len(candidates),
            "candidati_sopra_soglia": n_above,
            "controfattuali_1_seduta_disponibili": cf_available,
            **impact,
            "classe_validata": {
                "candidati": len(confirmed),
                "candidati_sopra_soglia": confirmed_above,
                **confirmed_impact,
            },
        },
        "validazione_manuale": validation,
        "segmenti_prompt": segments,
        "candidati": candidates,
    }


def _escape_md(value: object) -> str:
    return (
        str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")
    )


def render_markdown(payload: dict) -> str:
    summary = payload["riepilogo"]
    validation = payload["validazione_manuale"]
    method = payload["metodo"]
    lines = [
        "# Emittente come autore della previsione — misura #492",
        "",
        (
            f"Finestra: **{payload['finestra']['dal']} → {payload['finestra']['al_incluso']}**. "
            "Misura in sola lettura durante il freeze #171."
        ),
        "",
        "## Risultato",
        "",
        (
            f"L'euristica trova **{summary['candidati']} candidati** su "
            f"{summary['segnali_esaminati']} segnali di watchlist; "
            f"**{summary['candidati_sopra_soglia']}** hanno superato una soglia operativa. "
            f"{summary['candidati_con_decisione_buy_sell']} candidati hanno una decisione BUY/SELL "
            f"direttamente tracciata, per **${summary['notional_mosso_usd']:.2f}** mossi e "
            f"**${summary['pnl_realizzato_usd']:+.2f}** di P&L realizzato collegato."
        ),
        "",
        (
            f"Validazione manuale: **{validation['classe']}/{validation['n_classificati']}** "
            f"sono CLASSE; precisione dell'euristica **{validation['precisione_euristica']:.1%}**."
        ),
        (
            f"Sui soli casi confermati: **{summary['classe_validata']['candidati_sopra_soglia']}** "
            f"sopra soglia, **{summary['classe_validata']['candidati_con_decisione_buy_sell']}** "
            f"con BUY/SELL, **${summary['classe_validata']['notional_mosso_usd']:.2f}** mossi e "
            f"**${summary['classe_validata']['pnl_realizzato_usd']:+.2f}** realizzati."
        ),
        (
            "Il segmento post-Variante A contiene "
            f"**{payload['segmenti_prompt']['variante_a']['classe_validata']['candidati']}** casi "
            f"confermati e **${payload['segmenti_prompt']['variante_a']['classe_validata']['pnl_realizzato_usd']:+.2f}** "
            "realizzati: include il SELL GS della issue."
        ),
        "",
        "## Metodo e limiti",
        "",
        (
            "Il candidato richiede un alias societario sicuro come soggetto di un verbo di "
            "previsione/giudizio; i ticker corti non valgono come alias. Sono incluse le "
            "attribuzioni in coda. I complementi che citano esplicitamente l'emittente o i suoi "
            "fondamentali vengono esclusi. La precisione e' misurata sul campione manuale, non assunta."
        ),
        "",
        (
            f"Il lato lungo usa `{method['entry_threshold_source']}` = "
            f"{method['entry_threshold']:.3f}; il reversal usa {method['reversal_threshold']:.2f}. "
            "Il gate lungo e' uno snapshot del run: Redis non ne conserva la serie storica. "
            f"Prezzi: {method['fonte_prezzi']}. Decisioni collegate solo dalla FK `signal_id`; "
            "nessun match per vicinanza di score/orario."
        ),
        "",
        "## Candidati",
        "",
        "| signal | data UTC | ticker | manuale | score | conf. | model | std | soglia | decisioni | P&L | fwd 1 seduta | titolo | URL |",
        "|---:|---|---|---|---:|---:|---|---:|---|---|---:|---:|---|---|",
    ]
    for row in payload["candidati"]:
        cf = row["controfattuale_1_seduta"]["rendimento_1_seduta"]
        decisions = ", ".join(d["decision"] for d in row["decisioni"]) or "—"
        lines.append(
            f"| {row['signal_id']} | {_escape_md(row['generated_at'])} | {row['symbol']} | "
            f"{'CLASSE' if row['classe_validata_manualmente'] else 'NON CLASSE'} | "
            f"{row['score']:+.3f} | {row['confidence']:.3f} | {_escape_md(row['model_id'])} | "
            f"{row['ensemble_std'] if row['ensemble_std'] is not None else '—'} | "
            f"{_escape_md(row['soglia_operativa_superata'])} | "
            f"{decisions} | {row['pnl_realizzato_usd']:+.2f} | "
            f"{f'{cf:+.2%}' if cf is not None else '—'} | {_escape_md(row['title'])} | "
            f"<{_escape_md(row['url'])}> |"
        )
    candidate_by_id = {int(row["signal_id"]): row for row in payload["candidati"]}
    lines.extend(
        [
            "",
            "## Validazione manuale",
            "",
            "| signal | esito | nota | titolo |",
            "|---:|---|---|---|",
        ]
    )
    for label in validation["campione"]:
        row = candidate_by_id[label["signal_id"]]
        lines.append(
            f"| {label['signal_id']} | {'CLASSE' if label['classe'] else 'NON CLASSE'} | "
            f"{_escape_md(label['nota'])} | {_escape_md(row['title'])} |"
        )
    lines.extend(
        [
            "",
            "## Proposta, non applicata",
            "",
            method["proposta_non_applicata"],
            "",
            (
                "Nessun prompt, filtro live, soglia, peso, flag, cooldown o parametro di strategia "
                "e' stato modificato."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def scrivi(payload: dict) -> tuple[Path, Path]:
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n"
    )
    OUT_MD.write_text(render_markdown(payload))
    return OUT_JSON, OUT_MD


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=DEFAULT_SINCE.isoformat())
    parser.add_argument("--as-of", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--skip-alpaca", action="store_true")
    parser.add_argument("--candidates-only", action="store_true")
    args = parser.parse_args()
    since, until = date.fromisoformat(args.since), date.fromisoformat(args.as_of)
    if until < since:
        raise SystemExit("--as-of deve essere >= --since")

    if args.candidates_only:
        watchlist = _watchlist()
        aliases = leggi_alias(watchlist)
        threshold, _ = _read_entry_threshold()
        bounds = {
            "since": datetime.combine(
                since, datetime.min.time(), tzinfo=UTC
            ).isoformat(),
            "until": datetime.combine(
                until + timedelta(days=1), datetime.min.time(), tzinfo=UTC
            ).isoformat(),
        }
        signals = [
            row
            for row in _psql_json(QUERY_SIGNALS.format(**bounds))
            if str(row["symbol"]).upper() in watchlist
        ]
        print(
            json.dumps(
                _candidates(signals, aliases, threshold),
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        )
        return 0

    payload = misura(since, until, skip_alpaca=args.skip_alpaca)
    paths = scrivi(payload)
    summary = payload["riepilogo"]
    validation = payload["validazione_manuale"]
    print(
        f"candidati={summary['candidati']} sopra_soglia={summary['candidati_sopra_soglia']} "
        f"decisioni={summary['decisioni_buy_sell']} pnl=${summary['pnl_realizzato_usd']:+.2f} "
        f"precisione={validation['precisione_euristica']:.1%}\n"
        f"scritti: {paths[0]}\n         {paths[1]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
