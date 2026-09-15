"""Digest Telegram di cinque righe per il cron alpha-miss (#287, P4).

Il digest storico era ``head -c 3800`` dello stdout della sessione: lungo quanto
il modello aveva scritto fino li', troncato a un byte arbitrario, diverso da
seduta a seduta. Qui le cinque righe sono renderizzate da codice deterministico
da tre fonti che esistono gia' (dossier, riga materializzata di
market_daily.jsonl, scoreboard economico): l'operatore riceve sempre le stesse
cinque righe, nello stesso ordine, e un dato mancante e' ``DATA_INCOMPLETE``,
mai un numero inventato.

Modulo puro: nessun I/O. Il cron manda in Telegram cio' che riceve da qui.
"""

from __future__ import annotations

from typing import Any, Mapping

DATA_INCOMPLETE = "DATA_INCOMPLETE"

# Ordine canonico per il pareggio della causa prevalente: stabile, non "il
# primo che capita", cosicche' il digest sia riproducibile.
ORDINE_CAUSE = (
    "NO_NEWS",
    "THIN_NEUTRAL",
    "WRONG_SIGN",
    "FILTERED",
    "OUT_OF_STRATEGY_SCOPE",
)


def _riga_mercato(dossier: Mapping[str, Any]) -> str:
    mercato = dossier.get("mercato") or {}
    mover = mercato.get("mover_3pct")
    up = mercato.get("up")
    down = mercato.get("down")
    sigma = mercato.get("dispersione_sigma")
    data = dossier.get("data") or DATA_INCOMPLETE
    if not isinstance(mover, int) or not isinstance(up, int) or not isinstance(down, int):
        return f"🔎 Alpha-miss {data}: rendimenti {DATA_INCOMPLETE}"
    if not isinstance(sigma, (int, float)):
        return f"🔎 Alpha-miss {data}: {mover} mover ({up}↑ {down}↓), dispersione {DATA_INCOMPLETE}"
    return (
        f"🔎 Alpha-miss {data}: {mover} mover ({up}↑ {down}↓), "
        f"dispersione σ {sigma:.1%}"
    )


def _riga_miss(riga: Mapping[str, Any] | None) -> str:
    if not isinstance(riga, Mapping):
        return f"Miss: {DATA_INCOMPLETE} — catturati {DATA_INCOMPLETE}"
    miss = riga.get("miss") or {}
    totale = sum(miss.get(c) or 0 for c in ORDINE_CAUSE)
    prevalente = next(
        (c for c in ORDINE_CAUSE if (miss.get(c) or 0) > 0 and (miss.get(c) or 0) == max(miss.values())),
        None,
    )
    catturati = riga.get("catturati")
    catturati_str = str(catturati) if isinstance(catturati, int) else DATA_INCOMPLETE
    if prevalente is None:
        return f"Miss totale {totale} — nessuna causa prevalente; catturati {catturati_str}"
    return (
        f"Miss totale {totale} — prevalente {prevalente} {miss[prevalente]}; "
        f"catturati {catturati_str}"
    )


def _riga_tema(riga: Mapping[str, Any] | None) -> str:
    tema = riga.get("tema") if isinstance(riga, Mapping) else None
    return f"Tema: {tema}" if isinstance(tema, str) and tema.strip() else f"Tema: {DATA_INCOMPLETE}"


def _riga_findings(esiti_findings: list[Mapping[str, Any]]) -> str:
    if not esiti_findings:
        return "Findings oggi: nessuna segnalazione"
    parti: list[str] = []
    for e in esiti_findings:
        costo = e.get("costo_usd")
        fid = e.get("finding_id")
        if costo is None:
            parti.append(f"{fid} (non stimato)")
        else:
            parti.append(f"{fid} ${abs(float(costo)):.2f}")
    primo = esiti_findings[0]
    dettaglio = f" ({primo['titolo']})" if isinstance(primo.get("titolo"), str) else ""
    # La riga porta tutti gli id del giorno; il titolo solo del primo, per
    # non allungare oltre le cinque righe il contenuto informativo.
    return f"Findings oggi: {', '.join(parti)}{dettaglio}"


def _riga_carta(scoreboard: Mapping[str, Any] | None) -> str:
    sb = (scoreboard or {}).get("scoreboard") or {}
    giorno = sb.get("giorno") or {}
    s4 = sb.get("s4_vs_200") or {}
    n = giorno.get("n")
    denominatore = giorno.get("denominatore")
    if not isinstance(n, int) or not isinstance(denominatore, int):
        return f"Carta: giorno {DATA_INCOMPLETE} — S4 economico {DATA_INCOMPLETE}"
    cumulato = s4.get("cumulato")
    soglia = s4.get("soglia")
    if not isinstance(cumulato, (int, float)) or not isinstance(soglia, (int, float)):
        return (
            f"Carta: giorno {n}/{denominatore} — "
            f"S4 economico {DATA_INCOMPLETE}"
        )
    dentro = "DENTRO" if s4.get("within") else "FUORI"
    return (
        f"Carta: giorno {n}/{denominatore} — "
        f"S4 economico {cumulato:+.2f}$ vs ±{soglia:.0f}$ ({dentro})"
    )


def render_digest_telegram(
    dossier: Mapping[str, Any],
    riga_market: Mapping[str, Any] | None,
    *,
    esiti_findings: list[Mapping[str, Any]] | None = None,
    scoreboard: Mapping[str, Any] | None = None,
) -> list[str]:
    """Cinque righe deterministiche: mercato, miss, tema, findings, carta.

    ``esiti_findings`` sono i candidati applicati dal materializzatore (gli id
    del giorno); ``scoreboard`` e' il payload di economic_pnl.json.
    """
    return [
        _riga_mercato(dossier),
        _riga_miss(riga_market),
        _riga_tema(riga_market),
        _riga_findings(esiti_findings or []),
        _riga_carta(scoreboard),
    ]