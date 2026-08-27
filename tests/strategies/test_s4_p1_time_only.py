"""#297: challenger P1 D+2 time-only, in shadow.

P1 non e' una riproduzione di E0: e' un controfattuale. L'intento resta aperto
fino alla close di D0+2 sedute anche quando il runtime lo ha gia' venduto, e
l'unica uscita anticipata ammessa e' l'overlay di rischio comune.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.costs.calculator import CostBreakdown
from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    MarketSession,
    SubmittedIntent,
    reconcile_entry,
)
from src.strategies.s4.p1_time_only import (
    ExecutableQuote,
    P1MarketWindow,
    decide_p1,
    load_p1_policy_snapshot,
)

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "s4_exit_trial.yaml"
ENTRY_AT = datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC)
D0 = date(2026, 8, 25)
DUE = date(2026, 8, 27)
DUE_CLOSE = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)
NOW = datetime(2026, 8, 27, 20, 5, tzinfo=UTC)


class _CostModel:
    version = "cost-model:test-golden"

    def compute(self, *, symbol, notional, qty, fill_price, side):
        return CostBreakdown(
            spread_cost_bps=10.0,
            impact_cost_bps=0.0,
            regulatory_cost_usd=0.0,
            total_cost_bps=10.0,
            total_cost_usd=1.0 if side == "BUY" else 2.0,
        )


def _sessions() -> list[MarketSession]:
    return [
        MarketSession(
            session_date=date(2026, 8, day),
            open_at=datetime(2026, 8, day, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        )
        for day in (25, 26, 27, 28)
    ]


def _lifecycle(**overrides):
    intent = SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        symbol="AMD",
        order_id="entry-order-1",
        submitted_at=ENTRY_AT - timedelta(seconds=4),
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="alpaca_snapshot.latest_trade",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S4": 1.0},
    )
    event = reconcile_entry(
        intent,
        BrokerOrderSnapshot(
            order_id="entry-order-1",
            status="filled",
            filled_at=ENTRY_AT,
            filled_quantity=2.0,
            filled_avg_price=100.0,
        ),
        _sessions(),
        ENTRY_AT + timedelta(minutes=5),
        broker_position_quantity=2.0,
    )
    return replace(event, **overrides) if overrides else event


def _quote(minutes_before_close: int, price: float, low: float | None = None):
    return ExecutableQuote(
        at=DUE_CLOSE - timedelta(minutes=minutes_before_close),
        price=price,
        low=price if low is None else low,
    )


def _window(**overrides) -> P1MarketWindow:
    values = {
        "quotes": (
            _quote(400, 101.0),
            _quote(60, 108.0),
            _quote(1, 110.0),
        ),
        "session_close_at": DUE_CLOSE,
        "cutoff_at": DUE_CLOSE,
        "complete": True,
    }
    values.update(overrides)
    return P1MarketWindow(**values)


# ── Il contratto congelato, non una ricodifica ──────────────────────────────


def test_lo_snapshot_p1_viene_dal_contratto_e_dichiara_il_ruolo():
    snapshot = load_p1_policy_snapshot(CONTRACT_PATH)

    assert snapshot.version == "s4-exit-trial:1.0.0"
    assert snapshot.scope == "shadow_only"
    assert snapshot.promotable is True
    assert snapshot.d_hard_enabled is True
    assert snapshot.max_signal_age_drives_exit is False


def test_uno_snapshot_che_permettesse_al_silenzio_di_uscire_e_rifiutato(tmp_path):
    import yaml

    payload = yaml.safe_load(CONTRACT_PATH.read_bytes())
    payload["horizon"]["max_signal_age_drives_exit"] = True
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="max_signal_age"):
        load_p1_policy_snapshot(path)


def test_un_take_profit_acceso_nel_contratto_e_rifiutato(tmp_path):
    import yaml

    payload = yaml.safe_load(CONTRACT_PATH.read_bytes())
    payload["risk_overlay"]["take_profit"]["enabled"] = True
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="TP, trailing, scale-out"):
        load_p1_policy_snapshot(path)


# ── Criterio 3: nessun motivo E0 produce una SELL P1 ────────────────────────


def test_prima_della_scadenza_p1_resta_aperta_anche_se_il_runtime_ha_venduto():
    """E0 ha chiuso a D+1; P1 non lo sa e non deve saperlo."""
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(400, 101.0),), complete=False),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=datetime(2026, 8, 26, 15, 7, tzinfo=UTC),
    )

    assert event.policy_id == "P1"
    assert event.status == "OPEN"
    assert event.reason_code == "P1_HOLDING"
    assert event.virtual_exit_quantity == 0.0
    assert event.net_pnl is None


def test_la_scadenza_e_l_unica_uscita_ordinaria():
    event = decide_p1(
        _lifecycle(),
        _window(),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "CLOSED"
    assert event.reason_code == "P1_TIME_DUE"
    assert event.virtual_exit_quantity == pytest.approx(2.0)
    # 2 azioni comprate a 100, uscita all'ultimo eseguibile 110, costi 1 + 2
    assert event.gross_pnl == pytest.approx(20.0)
    assert event.net_pnl == pytest.approx(17.0)


# ── Criterio 5 e regola di prezzo: mai il closing print teorico ─────────────


def test_l_uscita_usa_l_ultimo_prezzo_eseguibile_non_il_close_teorico():
    """Il contratto vieta il closing print: vale l'ultimo scambio presentabile."""
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(400, 101.0), _quote(3, 107.5))),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.fill_price == pytest.approx(107.5)
    assert event.first_executable_price_source.startswith("alpaca_bars")


def test_se_nessun_prezzo_e_presentabile_entro_il_cutoff_vale_il_primo_successivo():
    tardi = ExecutableQuote(
        at=DUE_CLOSE + timedelta(minutes=30), price=112.0, low=112.0
    )
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(tardi,), cutoff_at=DUE_CLOSE),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "CLOSED"
    assert event.reason_code == "P1_TIME_DUE"
    assert event.fill_price == pytest.approx(112.0)
    assert event.details["exit_price_rule"] == "first_executable_after_cutoff"


# ── Overlay di rischio comune ──────────────────────────────────────────────


def test_il_d_hard_esce_prima_della_scadenza_e_non_e_attribuito_all_alpha():
    """d_hard e' identico fra le policy e non falsifica la tesi di P1."""
    sotto_stop = ExecutableQuote(
        at=datetime(2026, 8, 26, 14, 0, tzinfo=UTC), price=84.0, low=83.0
    )
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(2000, 99.0), sotto_stop, _quote(1, 110.0))),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "RISK_EXITED"
    assert event.reason_code == "P1_D_HARD"
    assert event.details["attributed_to_alpha_policy"] is False


def test_un_gap_oltre_lo_stop_riempie_al_primo_eseguibile_non_al_trigger():
    """`gap_beyond_stop` del contratto: il trigger non e' un prezzo."""
    gap = ExecutableQuote(
        at=datetime(2026, 8, 26, 14, 0, tzinfo=UTC), price=70.0, low=68.0
    )
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(gap,)),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.reason_code == "P1_D_HARD"
    # trigger a 85.0 (100 × (1 − 0.15)), ma il primo eseguibile e' 70.0
    assert event.fill_price == pytest.approx(70.0)
    assert event.details["d_hard_trigger_price"] == pytest.approx(85.0)


def test_uno_sfioramento_che_non_buca_lo_stop_non_esce():
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(2000, 90.0, low=85.5), _quote(1, 110.0))),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.reason_code == "P1_TIME_DUE"


# ── Censure e data failure ─────────────────────────────────────────────────


def test_un_ingresso_non_ricostruibile_e_censurato_non_misurato():
    event = decide_p1(
        _lifecycle(reconstructible=False),
        _window(),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "CENSORED"
    assert event.reason_code == "P1_ENTRY_NOT_RECONSTRUCTIBLE"
    assert event.comparable is False


def test_una_due_session_ignota_e_censurata_non_indovinata():
    event = decide_p1(
        _lifecycle(due_session=None),
        _window(),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "CENSORED"
    assert event.reason_code == "P1_DUE_SESSION_UNKNOWN"


def test_un_data_failure_alla_scadenza_non_falsifica_la_tesi_aperta():
    """Criterio 4: il time-stop resta osservabile, il P&L no."""
    event = decide_p1(
        _lifecycle(),
        _window(quotes=()),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=NOW,
    )

    assert event.status == "TRIGGERED"
    assert event.reason_code == "P1_EXIT_PRICE_MISSING"
    assert event.net_pnl is None
    assert event.comparable is False


def test_un_d_hard_non_calcolabile_non_diventa_uno_stop_a_zero():
    """Senza distanza di stop non si inventa un trigger a prezzo zero."""
    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(2000, 1.0), _quote(1, 110.0))),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=None,
        observed_at=NOW,
    )

    assert event.reason_code == "P1_TIME_DUE"
    assert event.details["d_hard_trigger_price"] is None
    assert "D_HARD_NOT_EVALUABLE" in event.divergence_reasons
    assert event.comparable is False


# ── Idempotenza e identita' ────────────────────────────────────────────────


def test_alla_scadenza_esiste_un_solo_close_anche_dopo_un_restart():
    args = (
        _lifecycle(),
        _window(),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
    )
    kwargs = {"d_hard_distance": 0.15, "observed_at": NOW}

    primo = decide_p1(*args, **kwargs)
    retry = decide_p1(*args, **{**kwargs, "observed_at": NOW + timedelta(hours=3)})

    assert retry.event_id == primo.event_id
    assert retry.virtual_exit_quantity == primo.virtual_exit_quantity


def test_la_proiezione_dichiara_l_osservazione_di_lifecycle_da_cui_nasce():
    """Stessa lezione di #374: senza, nessuna correzione a monte si propaga."""
    lifecycle = _lifecycle()
    snapshot = load_p1_policy_snapshot(CONTRACT_PATH)

    event = decide_p1(
        lifecycle, _window(), snapshot, _CostModel(),
        d_hard_distance=0.15, observed_at=NOW,
    )
    corretto = decide_p1(
        replace(lifecycle, event_id="lc-corretto"), _window(), snapshot, _CostModel(),
        d_hard_distance=0.15, observed_at=NOW,
    )

    assert event.details["entry_lifecycle_event_id"] == lifecycle.event_id
    assert corretto.event_id != event.event_id


def test_notional_e_costi_di_ingresso_restano_quelli_condivisi_con_p0():
    """Il contratto impone ingressi, fill e costi d'ingresso identici."""
    from src.strategies.s4.p0_baseline import load_p0_policy_snapshot, observe_p0_open

    lifecycle = _lifecycle()
    p0 = observe_p0_open(
        lifecycle, load_p0_policy_snapshot(CONTRACT_PATH), _CostModel(),
        runtime_trade_id=1,
    )
    p1 = decide_p1(
        lifecycle, _window(), load_p1_policy_snapshot(CONTRACT_PATH), _CostModel(),
        d_hard_distance=0.15, observed_at=NOW,
    )

    assert p1.initial_notional == pytest.approx(p0.initial_notional)
    assert p1.intent_id == p0.intent_id
    assert p1.d0 == p0.d0
    assert p1.details["entry_fill_id"] == p0.details["entry_fill_id"]


def test_un_fill_parziale_misura_la_quantita_effettiva():
    lifecycle = _lifecycle()
    parziale = replace(
        lifecycle,
        status="PARTIAL_FILL",
        reason_code="PARTIAL_FILL_OPEN",
        s4_virtual_quantity=1.0,
        reconstructible=False,
    )

    event = decide_p1(
        parziale, _window(), load_p1_policy_snapshot(CONTRACT_PATH), _CostModel(),
        d_hard_distance=0.15, observed_at=NOW,
    )

    assert event.status == "CENSORED"
    assert event.reason_code == "P1_ENTRY_NOT_RECONSTRUCTIBLE"


# ── Criterio 3, in forma strutturale ────────────────────────────────────────


@pytest.mark.parametrize(
    "motivo_e0",
    [
        "P0_TARGET_ZERO_NO_SIGNAL",
        "P0_TARGET_ZERO_EXPIRED",
        "P0_TARGET_ZERO_WHIPSAW",
        "P0_TARGET_ZERO_UNKNOWN",
        "P0_TARGET_ZERO_BELOW_ENTRY_GATE",
        "P0_TARGET_ZERO_FALLBACK_FILTERED",
        "P0_TARGET_ZERO_ENTRY_FRESHNESS_FILTERED",
        "P0_SENTIMENT_REVERSAL",
    ],
)
def test_nessun_motivo_di_uscita_e0_puo_chiudere_p1(motivo_e0):
    """Compreso il reversal ordinario: e' il counter *non* qualificato di P2.

    La garanzia e' strutturale prima che comportamentale — `decide_p1` non
    riceve affatto l'osservazione runtime — ma il test la fissa lo stesso: se
    un domani qualcuno passasse quel dato al modulo, questo fallirebbe.
    """
    del motivo_e0  # P1 non lo vede nemmeno: e' esattamente il punto

    event = decide_p1(
        _lifecycle(),
        _window(quotes=(_quote(400, 101.0),), complete=False),
        load_p1_policy_snapshot(CONTRACT_PATH),
        _CostModel(),
        d_hard_distance=0.15,
        observed_at=datetime(2026, 8, 26, 15, 7, tzinfo=UTC),
    )

    assert event.status == "OPEN"
    assert event.reason_code == "P1_HOLDING"


def test_il_modulo_non_conosce_l_osservazione_runtime():
    """La sola uscita anticipata ammessa e' l'overlay di rischio comune."""
    import inspect

    from src.strategies.s4 import p1_time_only

    firma = inspect.signature(p1_time_only.decide_p1).parameters
    assert "runtime" not in firma
    assert "RuntimeExitObservation" not in inspect.getsource(p1_time_only)


def test_nessun_campo_dell_esito_puo_chiedere_un_ordine():
    event = decide_p1(
        _lifecycle(), _window(), load_p1_policy_snapshot(CONTRACT_PATH), _CostModel(),
        d_hard_distance=0.15, observed_at=NOW,
    )

    assert event.shadow_order_id is None
    assert event.runtime_order_id is None
    assert event.runtime_decision_id is None
    assert event.runtime_quantity == 0.0
