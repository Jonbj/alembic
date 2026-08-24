"""Stimatore v2 di alpha accessibile e costo controfattuale (#280).

Modulo puro: riceve barre, timeline, size e costi gia' caricati, non tocca rete
ne' DB ne' file. La formula e' versionata (`ESTIMATOR_VERSION`): ogni stima
dichiara cutoff, entry, exit, size, vincoli, costi, formula e estimator_version,
cosi' i dollari accumulati nei ledger diventano confrontabili con le soglie
della carta di osservazione (#171).

Perche' esiste: il prompt alpha-miner stimava i miss moltiplicando il
rendimento close-to-close per una size plausibile. ORCL il 12/08 valeva $117,95
close-to-close ma solo $6,82 sul tratto intraday: sommare formule diverse rende
`costo_cumulato_usd` non confrontabile con la soglia $1.000. Questo stimatore
separa `gross` (tutto il movimento, upper bound) da `accessible` (la quota
realmente tradabile dal primo ciclo eleggibile, con la exit policy dichiarata)
da `net` (accessible al netto dei costi).

Freeze (#171): e' strumentazione, stima v2 prospettica e parallela. NON
riscrive le occurrence legacy ne' la serie `costo_usd` del prompt: il dossier
pubblica `opportunity_v2` accanto ai conteggi legacy.

Intraday: la quota accessibile richiede il prezzo al primo bar successivo al
primo ciclo realmente eleggibile. Dal #246 il dossier lo caba davvero: passa le
barre 5Min SIP e il ciclo eleggibile, che ha due fonti dichiarate e mai fuse —
`execution_decisions.tick_time` per i candidati con una decisione collegata,
`session_open` (primo ciclo da 15 minuti della seduta) per gli altri, tipicamente
i NO_NEWS. Quando barre o ciclo mancano, `accessible_opportunity_usd` resta
`None` con missingness esplicita — mai confuso con `gross`, mai inventato.

Serie legacy (#246 Q2): il ricalcolo del pregresso AFFIANCA, non sovrascrive.
Ogni stima porta un blocco `legacy` con il costo close-to-close calcolato come
lo calcolava il prompt alpha-miner, esplicitamente etichettato. La sintesi del
28/09 legge `opportunity_v2`; la serie legacy resta leggibile come traccia di
come il numero era stato prodotto prima. Nessuna occurrence di findings.json e
nessuna serie `costo_usd` viene riscritta da questo modulo — e' puro, non
scrive niente.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

ESTIMATOR_VERSION = "2.0"
ESTIMATOR_MODEL = "TradeCostCalculator/cost_model.yaml"

# Book long-only: non possiamo vendere allo scoperto un titolo non detenuto.
# Un ribasso non detenuto ha costo/opportunità accessibile ZERO verificato, non
# null: e' un'affermazione (non avremmo potuto guadagnare), non un dato mancante.
BOOK_SIDE_LONG = "long"
# Formula del prompt alpha-miner (serie legacy): rendimento close-to-close per
# una size plausibile. Sovrastima sistematicamente i miss di un motore RTH —
# ORCL 12/08: 117,95 $ contro ~6,82 $ realmente accessibili — ma resta pubblicata
# accanto alla v2, mai riscritta: e' la traccia di come il numero era nato (#246).
LEGACY_FORMULA = "costo_usd = |close_to_close| x size (prompt alpha-miner)"
EXIT_POLICY_EOD_CLOSE = "EOD_close"
FUNGIBILITY_NONE = "none — per-ticker, nessuna sostituzione tematica"

UTC = timezone.utc


class DailyBar(TypedDict, total=False):
    """Barra giornaliera OHLC + close precedente."""

    open: float
    high: float
    low: float
    close: float
    close_prec: float | None


class IntradayBar(TypedDict, total=False):
    """Barra intraday PIT (forma #277): identificata dal proprio istante di apertura."""

    timestamp: str  # ISO 8601 UTC
    open: float
    high: float
    low: float
    close: float


class CostSpec(TypedDict, total=False):
    """Costo roundtrip gia' computato dal chiamante via TradeCostCalculator.

    Convention coerente con il net_pnl live (src/store/pg_store.py):
    `total_usd` e' il `compute(side="SELL").total_cost_usd` (spread roundtrip +
    impact + regulatory sell). Passare None quando non c'e' trade.
    """

    spread_bps: float
    impact_bps: float
    regulatory_usd: float
    total_usd: float
    model: str
    adv_source: str


class OpportunityInput(TypedDict, total=False):
    """Input di una stima di opportunita'. Puro dato, nessun I/O."""

    symbol: str
    book_side: str  # "long" (long-only)
    held: bool
    daily: DailyBar
    intraday_bars: list[IntradayBar]  # ordinato per timestamp crescente
    eligible_cycle_at: str | None  # ISO UTC, primo ciclo realmente eleggibile
    eligible_cycle_source: str | None  # "execution_decisions.tick_time" | "session_open"
    size_usd: float  # size plausibile (slot S4 ~2% NAV)
    slot_fraction: float  # frazione di NAV (es. 0.02)
    cost: CostSpec | None  # costo roundtrip precomputato
    exit_policy: str  # "EOD_close"
    cutoff: str  # ISO UTC, bound point-in-time (es. market close)
    confidenza: str  # "misurata" | "attribuita" | "congetturale"
    fungibility_rule: str  # default FUNGIBILITY_NONE


def _as_utc(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _close_to_close(daily: DailyBar) -> float | None:
    prec, close = daily.get("close_prec"), daily.get("close")
    if prec is None or close is None or prec == 0:
        return None
    return close / prec - 1.0


def _first_eligible_bar(
    bars: list[IntradayBar], eligible_cycle_at: datetime, cutoff: datetime
) -> IntradayBar | None:
    """Primo bar con apertura >= eligible_cycle_at e <= cutoff (PIT, no look-ahead)."""
    elegible = _as_utc(eligible_cycle_at) if not isinstance(eligible_cycle_at, datetime) else eligible_cycle_at
    for bar in bars:
        bt = _as_utc(bar.get("timestamp"))
        if bt is None:
            continue
        if elegible <= bt <= cutoff:
            return bar
    return None


def compute_opportunity(inp: OpportunityInput) -> dict[str, Any]:
    """Calcola la stima v2 di opportunita' per un singolo candidato miss.

    Puro: niente I/O. Ogni stima porta estimator_version, formula e tutti i
    campi dichiarativi. Non somma attraverso opportunita' e non sostituisce
    esposizioni tematiche (fungibility_rule = "none").
    """
    daily: DailyBar = inp.get("daily") or {}
    size_usd = float(inp.get("size_usd", 0.0))
    held = bool(inp.get("held", False))
    book_side = inp.get("book_side", BOOK_SIDE_LONG)
    confidenza = inp.get("confidenza", "congetturale")
    fungibility = inp.get("fungibility_rule", FUNGIBILITY_NONE)
    cutoff_iso = inp.get("cutoff")
    cutoff = _as_utc(cutoff_iso)
    exit_policy = inp.get("exit_policy", EXIT_POLICY_EOD_CLOSE)

    rendimento = _close_to_close(daily)
    if rendimento is not None:
        gross = abs(rendimento) * size_usd
    else:
        gross = None

    # --- entry / accessible: vedi _accessible --------------------------------
    accessible, entry_block, exit_block, formula, missingness, trade_state = _accessible(
        inp, daily, rendimento, cutoff, exit_policy
    )

    # --- costi: solo se c'e' un trade accessibile -----------------------------
    cost_spec: CostSpec | None = inp.get("cost")
    costi_block, net = _net_cost(accessible, cost_spec, trade_state)

    return {
        "estimator_version": ESTIMATOR_VERSION,
        "symbol": inp.get("symbol"),
        "confidenza": confidenza,
        "fungibility_rule": fungibility,
        "formula": formula,
        "cutoff": cutoff_iso,
        "entry": entry_block,
        "exit": exit_block,
        "size": {
            "usd": size_usd,
            "slot_fraction": inp.get("slot_fraction"),
            "source": inp.get("size_source", "S4 fixed slot = bucket_pct/n_top x NAV"),
        },
        "vincoli": {
            "book_side": book_side,
            "held": held,
            "exit_policy": exit_policy,
        },
        "costi": costi_block,
        "trade_state": trade_state,
        "gross_opportunity_usd": gross,
        "accessible_opportunity_usd": accessible,
        "net_opportunity_usd": net,
        "missingness": missingness,
        # Serie legacy AFFIANCATA (#246 Q2): stesso numero che il prompt
        # alpha-miner avrebbe scritto, etichettato per quello che e'. Non
        # sostituisce le occurrence gia' scritte e non viene sostituito dalla v2:
        # le due serie convivono, e la sintesi del 28/09 legge la v2.
        "legacy": {
            "costo_usd": gross,
            "formula": LEGACY_FORMULA,
            "serie": "affiancata — la v2 non riscrive le occurrence legacy",
            "letta_dalla_sintesi_28_09": False,
        },
    }


# Trade-state canonici: permettono a _net_cost di distinguere "no trade
# possibile" (long-only ribasso) da "trade simulato a pareggio" (P&L lordo 0
# ma costo roundtrip reale). Senza questo segnale, accessible == 0.0 e' un
# ambiguo fra i due casi (#280 review codex, opportunity.py riga 299).
TRADE_STATE_NO_TRADE = "no_trade"            # long-only ribasso: non eseguibile
TRADE_STATE_SIMULATED = "simulated"          # trade eseguito davvero, P&L puo' essere 0
TRADE_STATE_HELD = "held"                    # posizione gia' detenuta: non e' un miss
TRADE_STATE_MISSING = "missing"              # dati insufficienti (intraday, eligible_cycle)


def _accessible(
    inp: OpportunityInput,
    daily: DailyBar,
    rendimento: float | None,
    cutoff: datetime | None,
    exit_policy: str,
) -> tuple[float | None, dict, dict, str, list[str], str]:
    """Determina la quota accessibile, l'entry, l'exit e la formula applicata.

    Ritorna (accessible_usd, entry_block, exit_block, formula, missingness,
    trade_state). Il trade_state distingue "no_trade" (long-only ribasso) da
    "simulated" (trade davvero eseguito, anche con P&L lordo zero) — i due
    casi producono entrambi accessible=0.0 ma semantiche opposte: il primo
    non ha costi, il secondo ha il costo roundtrip.
    """
    held = bool(inp.get("held", False))
    book_side = inp.get("book_side", BOOK_SIDE_LONG)
    size_usd = float(inp.get("size_usd", 0.0))
    missingness: list[str] = []

    # Position gia' detenuta: non e' un alpha-miss, l'opportunita' e' passiva
    # (misurata altrove, M4). Nessuna stima congetturale qui.
    if held:
        return (
            None,
            {"price": None, "source": None, "timestamp": None, "bar_timestamp": None,
             "missing_reason": "held_position_not_an_alpha_miss"},
            {"price": None, "source": None, "policy": exit_policy},
            "held: not a miss — accessible measured as passive exposure (M4), not conjectured here",
            ["held_position_not_an_alpha_miss"],
            TRADE_STATE_HELD,
        )

    # Ribasso non detenuto in book long-only: ZERO verificato, non null.
    # Non possiamo vendere allo scoperto: il ribasso non era catturabile.
    if rendimento is not None and rendimento < 0 and book_side == BOOK_SIDE_LONG:
        return (
            0.0,
            {"price": None, "source": None, "timestamp": None, "bar_timestamp": None,
             "missing_reason": "long_only_no_short_downside_not_held"},
            {"price": None, "source": "n/a — no trade (long-only, down, not held)", "policy": exit_policy},
            "gross = |close_to_close| x size; accessible = 0 (long_only, no short, not held); net = 0",
            [],
            TRADE_STATE_NO_TRADE,
        )

    # Rialzo non detenuto: serve l'entry al primo ciclo eleggibile (intraday, #277).
    bars: list[IntradayBar] = inp.get("intraday_bars") or []
    eligible_cycle_at = inp.get("eligible_cycle_at")
    exit_price = daily.get("close")
    exit_block = {"price": exit_price, "source": "daily_close", "policy": exit_policy}

    if not bars or eligible_cycle_at is None or cutoff is None:
        missingness.append("intraday_bars_not_available_eligible_cycle_unpriced")
        return (
            None,
            {"price": None, "source": None, "timestamp": None, "bar_timestamp": None,
             "missing_reason": "intraday_bars_not_available_eligible_cycle_unpriced"},
            exit_block,
            "gross = |close_to_close| x size; accessible = NOT COMPUTABLE without intraday bar at eligible cycle (blocked by #277); net = None",
            missingness,
            TRADE_STATE_MISSING,
        )

    bar = _first_eligible_bar(bars, _as_utc(eligible_cycle_at), cutoff)
    if bar is None:
        missingness.append("no_intraday_bar_in_eligible_window")
        return (
            None,
            {"price": None, "source": None, "timestamp": None, "bar_timestamp": None,
             "missing_reason": "no_intraday_bar_in_eligible_window"},
            exit_block,
            "gross = |close_to_close| x size; accessible = NOT COMPUTABLE (no bar in [eligible_cycle, cutoff]); net = None",
            missingness,
            TRADE_STATE_MISSING,
        )

    entry_price = float(bar["open"])
    if entry_price <= 0:
        missingness.append("entry_price_not_positive")
        return (
            None,
            {"price": None, "source": "intraday_open", "timestamp": eligible_cycle_at,
             "bar_timestamp": bar.get("timestamp"), "missing_reason": "entry_price_not_positive"},
            exit_block,
            "gross = |close_to_close| x size; accessible = NOT COMPUTABLE (entry price <= 0); net = None",
            missingness,
            TRADE_STATE_MISSING,
        )

    shares = size_usd / entry_price if entry_price else None
    accessible = (exit_price - entry_price) * shares if (exit_price is not None and shares is not None) else None
    if accessible is None:
        missingness.append("exit_price_missing")

    entry_block = {
        "price": entry_price,
        "source": "intraday_open_at_first_eligible_bar",
        "timestamp": eligible_cycle_at,
        # Da dove viene il ciclo: una decisione osservata o il primo ciclo della
        # seduta. Le due popolazioni non vanno mischiate in analisi (#246).
        "eligible_cycle_source": inp.get("eligible_cycle_source"),
        "bar_timestamp": bar.get("timestamp"),
        "missing_reason": None,
    }
    formula = (
        "gross = |close_to_close| x size; "
        "accessible = (exit_close - entry_open_at_eligible_cycle) x shares; "
        "net = accessible - roundtrip_cost"
    )
    return accessible, entry_block, exit_block, formula, missingness, TRADE_STATE_SIMULATED


def _net_cost(
    accessible: float | None, cost_spec: CostSpec | None, trade_state: str
) -> tuple[dict, float | None]:
    """Costi e net, discriminati dallo stato del trade.

    trade_state decide il contratto:
    - "no_trade" (long-only ribasso, non eseguibile): costo 0.0 verificato,
      net = 0.0. Non stiamo mentendo: il trade non e' avvenuto per vincolo
      di costruzione, non per pareggio.
    - "held" / "missing": non c'e' stima di opportunita', costo e net sono None.
    - "simulated": trade davvero eseguito (anche con P&L lordo 0). Il costo
      roundtrip va sottratto: net = accessible - cost. Se il modello di costo
      non e' stato passato (cost_spec None), net resta None con costi None —
      non inventiamo costi per non nascondere la mancanza.

    Il check precedente `accessible == 0.0` collassava "no_trade" e "simulated
    a pareggio" nello stesso ramo: per un trade davvero eseguito a P&L zero,
    il costo roundtrip spariva e net tornava 0 invece di -cost (#280 review
    codex, opportunity.py riga 299).
    """
    if trade_state == TRADE_STATE_NO_TRADE:
        return {"total_usd": 0.0, "model": ESTIMATOR_MODEL,
                "spread_bps": 0.0, "impact_bps": 0.0, "regulatory_usd": 0.0,
                "adv_source": "n/a — no trade"}, 0.0
    if trade_state in (TRADE_STATE_HELD, TRADE_STATE_MISSING):
        return {"total_usd": None, "model": ESTIMATOR_MODEL,
                "spread_bps": None, "impact_bps": None, "regulatory_usd": None,
                "adv_source": None}, None
    # TRADE_STATE_SIMULATED: il trade c'e' stato, applico il costo roundtrip.
    if accessible is None or cost_spec is None:
        return {"total_usd": None, "model": ESTIMATOR_MODEL,
                "spread_bps": None, "impact_bps": None, "regulatory_usd": None,
                "adv_source": None}, None
    total = float(cost_spec.get("total_usd", 0.0) or 0.0)
    return (
        {
            "total_usd": total,
            "model": cost_spec.get("model", ESTIMATOR_MODEL),
            "spread_bps": cost_spec.get("spread_bps"),
            "impact_bps": cost_spec.get("impact_bps"),
            "regulatory_usd": cost_spec.get("regulatory_usd"),
            "adv_source": cost_spec.get("adv_source", "default_fallback"),
        },
        accessible - total,
    )