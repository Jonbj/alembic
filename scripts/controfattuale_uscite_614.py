#!/usr/bin/env python3
"""Controfattuale sulle uscite (portfolio_sell) — #614, Fase 2, misura.

Pre-registrazioni (l'ordine conta, la misura e' l'ultima):
- disegno: docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md
- misura:  docs/evidence/PREREGISTRAZIONE_MISURA_CONTROFATTUALE_USCITE_2026-09-24.md

FAIL-CLOSED SUL CHARTER (DoD 5 della issue): i rami non vengono eseguiti finché
l'operatore non registra la propria riga in docs/evidence/OBSERVATION_CHARTER.md
(una riga che citi insieme #614 e il controfattuale). Senza quella riga lo script
esce con codice 2 PRIMA di scaricare qualunque dato.

Cosa fa, nell'ordine:
1. verifica la riga charter;
2. riverifica il cancello di riproducibilità §4 sulla finestra richiesta
   (stesso metodo del runner del cancello, `scripts/replay_gate_614.py`);
   se il cancello fallisce, i rami non partono;
3. scarica i fill broker e li etichetta col motivo d'uscita dal DB diagnostico
   (trades.exit_order_ids, join per id ordine);
4. esegue il ramo di controllo (orizzonte 0) e i rami H_N per N in 1/2/5/10/21;
5. scrive l'artefatto JSON con serie, displacement, censure, metriche Q2-rec-4
   e inferenza Newey-West lag=N (|t| >= 3, MDE = 3·SE).

Sola lettura: nessuna scrittura su DB o Redis; l'unico output e' l'artefatto.

Uso (dall'host, con le chiavi del .env del checkout principale):
    export $(grep -E '^(ALPACA_API_KEY|ALPACA_SECRET_KEY|ALPACA_BASE_URL)=' ../.env)
    ../../.venv/bin/python scripts/controfattuale_uscite_614.py \
        --start 2026-08-03 --end <ultima seduta completa> \
        --output docs/research/<data>-controfattuale-uscite.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest.costs.realistic import RealisticCostModel
from src.backtest.engine.exit_counterfactual import (
    EsitoRamo,
    FillConMotivo,
    replay_ramo,
)
from src.backtest.engine.exit_replay import (
    BrokerFill,
    equity_di_seduta,
    evaluate_gate,
    initial_cash,
    reconstruct_start_quantities,
    replay,
)
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.performance.ic import compute_newey_west_hac
# Le funzioni di I/O del cancello si riusano cosi' com'erano (regola #169/#467):
# scaricare due volte gli ordini, o con un filtro diverso, e' esattamente il
# tipo di divergenza che il cancello esiste per impedire.
from scripts.replay_gate_614 import (
    closes_da_barre,
    fills_da_ordini,
    inizio_scarico_ordini,
    seduta_precedente,
    session_closes_da_calendario,
    _client_trading,
    _scarica_barre,
    _scarica_ordini,
    _scarica_ph,
)

# §3 della pre-registrazione di misura: orizzonti dichiarati nel 2026-09-16 §3,
# nessun altro. Il ramo di controllo (0) non e' nella griglia: e' il replay reale.
ORIZZONTI = (1, 2, 5, 10, 21)

CHARTER = Path("docs/evidence/OBSERVATION_CHARTER.md")

# Barra della significativita' (Q3-HARVEY-LIU-ZHU, prassi del repo).
T_BAR = 3.0

DSN_DEFAULT = "postgresql://trading:trading@localhost:5432/trading"

QUERY_MOTIVI = """
SELECT u.oid AS order_id, t.exit_reason
FROM trades t, unnest(t.exit_order_ids) AS u(oid)
WHERE t.exit_time > %s AND t.exit_time <= %s AND t.exit_reason IS NOT NULL
"""


# ---------------------------------------------------------------------------
# Funzioni pure (testate in tests/scripts/test_controfattuale_uscite_614.py)
# ---------------------------------------------------------------------------


def riga_charter_presente(testo: str) -> tuple[bool, str | None]:
    """La riga dell'operatore cita #614 e il controfattuale sulla stessa riga.

    Non accetta surrogati: una riga che nomina un controfattuale per un'altra
    issue (#512) non autorizza questa misura.
    """
    for riga in testo.splitlines():
        if "614" in riga and re.search(r"controfattual", riga, re.IGNORECASE):
            return True, riga.strip()
    return False, None


def motivi_da_righe_trades(
    righe: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Righe (order_id, exit_reason) gia' appiattite -> dizionario id -> motivo.

    Le righe senza motivo non entrano: un fill senza etichetta resta reale
    (fail-closed sull'etichetta, §2).
    """
    motivi: dict[str, str] = {}
    for r in righe:
        if r["exit_reason"] is None:
            continue
        motivi[r["order_id"]] = r["exit_reason"]
    return motivi


def vendita_ipotetica(
    modello: RealisticCostModel,
    simbolo: str,
    quantita: float,
    close: float,
    campana: datetime,
) -> BrokerFill:
    """La vendita ritardata passa dal modello dei costi (§4: mai zero)."""
    ordine = Order(
        order_id=f"ipotetico-614-{simbolo}",
        timestamp=campana,
        symbol=simbolo,
        side=OrderSide.SELL,
        quantity=quantita,
        strategy_id="controfattuale_614",
    )
    mercato = MarketSnapshot(
        timestamp=campana, prices={simbolo: close}, volumes={}, adv_20d={}
    )
    fill = modello.simulate_fill(ordine, mercato)
    return BrokerFill(
        timestamp=campana,
        symbol=simbolo,
        side=OrderSide.SELL,
        quantity=fill.quantity,
        fill_price=fill.fill_price,
        commission=fill.commission,
    )


def diagnostica_etichette(fills: Sequence[FillConMotivo]) -> dict[str, Any]:
    """Copertura del join ordini->trades: quante vendite hanno un motivo.

    Le vendite senza etichetta restano reali nel controfattuale (fail-closed
    sull'etichetta): questa diagnostica rende visibile quante sono, perche' se
    il join perdesse delle vendite il ramo H_N ritarderebbe troppo poco.
    """
    vendite = [f for f in fills if f.side == OrderSide.SELL]
    per_motivo: dict[str, int] = {}
    for f in vendite:
        if f.exit_reason is not None:
            per_motivo[f.exit_reason] = per_motivo.get(f.exit_reason, 0) + 1
    return {
        "vendite": len(vendite),
        "vendite_etichettate": sum(per_motivo.values()),
        "vendite_senza_etichetta": len(vendite) - sum(per_motivo.values()),
        "per_motivo": per_motivo,
    }


def dati_per_inferenza(
    equity_ramo: Mapping[date, float],
    equity_controllo: Mapping[date, float],
) -> tuple[list[date], list[float]]:
    """Diff giornaliera ramo meno controllo, allineata per seduta comune."""
    giorni = sorted(set(equity_ramo) & set(equity_controllo))
    return giorni, [equity_ramo[g] - equity_controllo[g] for g in giorni]


def inferenza(diff: Sequence[float], lag: int) -> dict[str, Any]:
    """§5: t = media / SE Newey-West (lag = orizzonte), MDE = 3·SE.

    SE nullo (varianza zero) => t indefinito, non infinito: l'esito onesto e'
    "non decidibile", mai un t gigante per costruzione.
    """
    n = len(diff)
    se = compute_newey_west_hac(list(diff), lag=lag)
    media = sum(diff) / n if n else 0.0
    t = media / se if se > 0 else None
    return {
        "n": n,
        "media": media,
        "se_nw": se,
        "t": t,
        "mde": T_BAR * se,
        "barra_t": T_BAR,
        "lag": lag,
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _motivi_dal_db(dsn: str, inizio: datetime, fine: datetime) -> dict[str, str]:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    con = psycopg2.connect(dsn)
    try:
        with con.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(QUERY_MOTIVI, (inizio, fine))
            return motivi_da_righe_trades(cur.fetchall())
    finally:
        con.close()


def _ramo_in_artefatto(
    esito: EsitoRamo, inf: Mapping[str, Any] | None
) -> dict[str, Any]:
    return {
        "orizzonte": esito.orizzonte,
        "equity_finale": esito.equity_finale,
        "capitale_medio_impiegato": esito.capitale_medio_impiegato,
        "cash_drag_medio": esito.cash_drag_medio,
        "vendite_ritardate": [
            {
                "simbolo": v.simbolo,
                "quantita_soppressa": v.quantita_soppressa,
                "seduta_originale": v.seduta_originale.isoformat(),
                "seduta_uscita": v.seduta_uscita.isoformat() if v.seduta_uscita else None,
            }
            for v in esito.vendite_ritardate
        ],
        "estensioni_censurate": esito.estensioni_censurate,
        "fill_ipotetici": [
            {
                "simbolo": f.symbol,
                "quantita": f.quantity,
                "prezzo": f.fill_price,
                "commissione": f.commission,
                "seduta": f.timestamp.date().isoformat(),
            }
            for f in esito.fill_ipotetici
        ],
        "buy_saltati": [
            {
                "giorno": e.giorno.isoformat(), "simbolo": e.simbolo,
                "tipo": e.tipo, "quantita": e.quantita, "dettaglio": e.dettaglio,
            }
            for e in esito.buy_saltati
        ],
        "sell_troncate": [
            {
                "giorno": e.giorno.isoformat(), "simbolo": e.simbolo,
                "tipo": e.tipo, "quantita": e.quantita, "dettaglio": e.dettaglio,
            }
            for e in esito.sell_troncate
        ],
        "inferenza": dict(inf) if inf is not None else None,
        "serie_equity": [
            {"giorno": r.giorno.isoformat(), "equity": r.equity} for r in esito.serie
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Controfattuale uscite #614 (misura)")
    parser.add_argument("--start", required=True, help="Prima seduta della finestra (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Ultima seduta COMPLETA della finestra")
    parser.add_argument("--output", required=True, help="Percorso dell'artefatto JSON")
    parser.add_argument("--dsn", default=DSN_DEFAULT, help="DSN del DB diagnostico (sola lettura)")
    parser.add_argument("--tolleranza-pct", type=float, default=2.0, help="Tolleranza %% del cancello (pre-registrata 2)")
    parser.add_argument(
        "--solo-controllo",
        action="store_true",
        help="Solo diagnostica: cancello riverificato + join etichette, NESSUN ramo H_N. "
        "Non produce numeri controfattuali e non richiede la riga charter.",
    )
    args = parser.parse_args()

    # 1. fail-closed sul charter, prima di toccare la rete: vale solo per i rami
    presente, riga = riga_charter_presente(CHARTER.read_text())
    if not args.solo_controllo and not presente:
        print(
            "RIFIUTATO: la misura richiede la riga dell'operatore in "
            f"{CHARTER} (una riga che citi #614 e il controfattuale). "
            "DoD 5 della issue #614; vedi PREREGISTRAZIONE_MISURA_CONTROFATTUALE_USCITE_2026-09-24.md.",
            file=sys.stderr,
        )
        return 2

    inizio = date.fromisoformat(args.start)
    fine = date.fromisoformat(args.end)

    tc = _client_trading()
    calendario = tc.get(
        "/calendar",
        data={
            "start": (inizio - timedelta(days=10)).isoformat(),
            "end": (fine + timedelta(days=3)).isoformat(),
        },
    )
    session_closes = session_closes_da_calendario(list(calendario))
    sedute = sorted(session_closes)
    if inizio not in session_closes or fine not in session_closes:
        raise SystemExit(f"--start/--end devono essere sedute: {inizio}, {fine}")
    ancoraggio = seduta_precedente(inizio, sedute)
    sedute_finestra = [g for g in sedute if ancoraggio < g <= fine]

    # 2. cancello riverificato sulla stessa finestra, prima dei rami
    ordini = _scarica_ordini(
        tc, dopo=inizio_scarico_ordini(session_closes[ancoraggio]), fino=datetime.now(timezone.utc)
    )
    fills_tutti = fills_da_ordini(ordini)
    fills_finestra = [
        f for f in fills_tutti if session_closes[ancoraggio] < f.timestamp <= session_closes[fine]
    ]

    posizioni_correnti = {
        p["symbol"]: float(p["qty"]) for p in tc.get_all_positions() if float(p["qty"]) != 0
    }
    qty_inizio = reconstruct_start_quantities(
        posizioni_correnti, fills_tutti, after=session_closes[ancoraggio]
    )
    simboli = sorted(
        set(qty_inizio) | set(posizioni_correnti) | {f.symbol for f in fills_tutti}
    )
    barre = _scarica_barre(simboli, inizio=ancoraggio, fine=fine)
    closes = closes_da_barre(barre)
    if ancoraggio not in closes:
        raise SystemExit(f"barre mancanti per la seduta di ancoraggio {ancoraggio}")

    ph = _scarica_ph(tc, inizio=ancoraggio, fine=fine)
    equity_inizio_broker = equity_di_seduta(ph, ancoraggio)
    equity_fine_broker = equity_di_seduta(ph, fine)
    cash_inizio = initial_cash(equity_inizio_broker, qty_inizio, closes[ancoraggio])

    serie_gate, _ = replay(
        start_qty=qty_inizio,
        start_cash=cash_inizio,
        start_closes=closes[ancoraggio],
        fills=fills_finestra,
        closes_by_day={g: closes.get(g, {}) for g in sedute_finestra},
        session_closes={g: session_closes[g] for g in sedute_finestra},
    )
    esito_gate = evaluate_gate(
        replay_equity=serie_gate[-1].equity,
        broker_equity=equity_fine_broker,
        tolleranza_pct=args.tolleranza_pct,
    )
    print(
        f"Cancello riverificato: delta {esito_gate.delta:+,.2f} "
        f"({esito_gate.delta_pct:+.4f}%) -> "
        f"{'SUPERATO' if esito_gate.superato else 'FALLITO'}"
    )
    if not esito_gate.superato:
        print("RIFIUTATO: cancello di riproducibilita' fallito sulla finestra; niente rami.")
        return 3

    # 3. etichette dei motivi d'uscita dal DB diagnostico
    motivi = _motivi_dal_db(
        args.dsn, inizio=session_closes[ancoraggio], fine=session_closes[fine]
    )
    fills_etichettati = [
        f
        for f in fills_da_ordini(ordini, motivi=motivi)
        if session_closes[ancoraggio] < f.timestamp <= session_closes[fine]
    ]
    etichette = diagnostica_etichette(fills_etichettati)
    print(
        f"Vendite in finestra: {etichette['vendite']} "
        f"(etichettate {etichette['vendite_etichettate']}, "
        f"senza etichetta {etichette['vendite_senza_etichetta']}); "
        f"portfolio_sell: {etichette['per_motivo'].get('portfolio_sell', 0)}"
    )

    if args.solo_controllo:
        # diagnostica: cancello + join etichette, nessun ramo, nessun numero nuovo
        artefatto_solo = {
            "issue": 614,
            "fase": "solo-controllo",
            "nota": (
                "Diagnostica della pipeline: cancello riverificato e copertura del join "
                "ordini->trades. Nessun ramo H_N e' stato eseguito."
            ),
            "finestra": {
                "sedute": [inizio.isoformat(), fine.isoformat()],
                "ancoraggio": ancoraggio.isoformat(),
                "n_sedute": len(sedute_finestra),
            },
            "cancello_riverificato": {
                "replay_equity": esito_gate.replay_equity,
                "broker_equity": esito_gate.broker_equity,
                "delta": esito_gate.delta,
                "delta_pct": esito_gate.delta_pct,
                "superato": esito_gate.superato,
            },
            "etichette": etichette,
            "motivi_nel_db": len(motivi),
            "generato_il": datetime.now(timezone.utc).isoformat(),
        }
        uscita = Path(args.output)
        uscita.parent.mkdir(parents=True, exist_ok=True)
        with open(uscita, "w") as f:
            json.dump(artefatto_solo, f, indent=2, ensure_ascii=False)
        print(f"Artefatto: {uscita}")
        return 0

    modello = RealisticCostModel(config_path=Path("config/cost_model.yaml"))
    kwargs = dict(
        start_qty=qty_inizio,
        start_cash=cash_inizio,
        start_closes=closes[ancoraggio],
        closes_by_day={g: closes.get(g, {}) for g in sedute_finestra},
        session_closes={g: session_closes[g] for g in sedute_finestra},
    )

    def prezza(simbolo: str, quantita: float, close: float, campana: datetime) -> BrokerFill:
        return vendita_ipotetica(modello, simbolo, quantita, close, campana)

    # 4. controllo (orizzonte 0) e rami H_N
    esito_controllo, _ = replay_ramo(
        fills=fills_etichettati, orizzonte=0, prezza_vendita=prezza, **kwargs
    )
    equity_controllo = {r.giorno: r.equity for r in esito_controllo.serie}

    rami_artefatto: list[dict[str, Any]] = []
    for n in ORIZZONTI:
        esito, _ = replay_ramo(
            fills=fills_etichettati, orizzonte=n, prezza_vendita=prezza, **kwargs
        )
        giorni, diff = dati_per_inferenza(
            {r.giorno: r.equity for r in esito.serie}, equity_controllo
        )
        inf = inferenza(diff, lag=n)
        blocco = _ramo_in_artefatto(esito, inf)
        blocco["delta_vs_controllo"] = round(esito.equity_finale - esito_controllo.equity_finale, 2)
        blocco["serie_diff_vs_controllo"] = [
            {"giorno": g.isoformat(), "diff": d} for g, d in zip(giorni, diff)
        ]
        rami_artefatto.append(blocco)
        print(
            f"H_{n}: equity {esito.equity_finale:,.2f} "
            f"(delta {esito.equity_finale - esito_controllo.equity_finale:+,.2f}, "
            f"t={inf['t'] if inf['t'] is not None else 'n.d.'}, "
            f"censure {esito.estensioni_censurate}, "
            f"buy saltati {len(esito.buy_saltati)})"
        )

    # 5. artefatto
    artefatto = {
        "issue": 614,
        "fase": "controfattuale-uscite",
        "pre_registrazioni": [
            "docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md",
            "docs/evidence/PREREGISTRAZIONE_MISURA_CONTROFATTUALE_USCITE_2026-09-24.md",
        ],
        "riga_charter": riga,
        "finestra": {
            "sedute": [inizio.isoformat(), fine.isoformat()],
            "ancoraggio": ancoraggio.isoformat(),
            "n_sedute": len(sedute_finestra),
        },
        "cancello_riverificato": {
            "replay_equity": esito_gate.replay_equity,
            "broker_equity": esito_gate.broker_equity,
            "delta": esito_gate.delta,
            "delta_pct": esito_gate.delta_pct,
            "superato": esito_gate.superato,
        },
        "conteggi": {
            "fill_reali_finestra": len(fills_finestra),
            "portfolio_sell_etichettate": etichette["per_motivo"].get("portfolio_sell", 0),
            "motivi_nel_db": len(motivi),
        },
        "controllo": _ramo_in_artefatto(esito_controllo, None) | {"delta_vs_controllo": 0.0},
        "rami": rami_artefatto,
        "predizioni_pre_registrate": [
            "P1: il delta sara' dominato da costo di transazione e beta, non alpha (Q1-rec-2)",
            "P2: se H_10/H_21 vincono, attribuzione a costo/beta finche' non dimostrato (Q5-rec-3)",
            "P3: magnitudine attesa dell'ordine dei bps/giorno; oltre, sospetto artefatto (Q5-rec-5)",
        ],
        "nota_insufficient_n": (
            "Se |delta| < MDE l'esito e' NON DECIDIBILE (INSUFFICIENT_N), mai 'nessun effetto' "
            "(§5 della pre-registrazione di misura; il campione utile e' il numero di sedute)"
        ),
        "generato_il": datetime.now(timezone.utc).isoformat(),
    }

    uscita = Path(args.output)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    with open(uscita, "w") as f:
        json.dump(artefatto, f, indent=2, ensure_ascii=False)
    print(f"Artefatto: {uscita}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
