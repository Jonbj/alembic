#!/usr/bin/env python3
"""Sensitivity della domanda di uscita n.1 al trattamento dei non-decidibili (#244).

#244 spezza THIN_NEUTRAL in tre bucket, ma uno dei tre — OFF_TOPIC_NON_DECIDIBILE
— e' per costruzione una dichiarazione di ignoranza: le righe `source_metadata`
scorano uno snippet troncato che il dossier non conserva, quindi «il testo
parlava davvero di questo ticker?» non ha risposta su questo dato (serve QX-01,
#30). Il rischio e' ovvio: se il verdetto del 28/09 dipende da come si trattano
quelle righe, allora non e' il verdetto a essere fragile — e' la misura.

Questo script rende quella dipendenza esplicita, ricalcolando la domanda n.1 in
tre varianti che coprono i due estremi e l'astensione:

    A  non-decidibili -> THIN_NEUTRAL   (estremo «erano notizie vere e fiacche»,
                                         = comportamento pre-#244)
    B  non-decidibili -> OFF_TOPIC      (estremo «erano tutte fuori tema»)
    C  non-decidibili esclusi           (astensione: escono dal denominatore,
                                         il giorno si giudica sui soli decidibili)

Domanda di uscita n.1 (`docs/evidence/OBSERVATION_CHARTER.md`, riga 122):

    «Esiste alpha nella news editoriale su questa watchlist?»
    Falsificazione: se alla scadenza NO_NEWS resta la causa di miss dominante
    in >=60% dei giorni E il P&L economico di S4 resta dentro +/-$200, la
    risposta e' no.

Le due gambe sono in AND. La gamba P&L non dipende dalla classificazione: e'
la stessa in tutte e tre le varianti, e viene riportata per completezza del
verdetto. La gamba che le varianti muovono e' la prima.

NESSUNA soglia viene toccata (freeze #171): 60% e +/-$200 sono quelle
pre-registrate, e le tre varianti ri-partizionano solo righe gia' classificate.

Uso:
    uv run python scripts/off_topic_sensitivity.py
    uv run python scripts/off_topic_sensitivity.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.dossier.miss_cause import (  # noqa: E402
    OFF_TOPIC,
    OFF_TOPIC_NON_DECIDIBILE,
    THIN_NEUTRAL,
    count_by_cause,
    dominant_cause,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOSSIER_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
PNL_FILE = PROJECT_DIR / "docs" / "evidence" / "economic_pnl.json"

# Soglie pre-registrate nella carta di osservazione. NON sono parametri di
# questo script: sono la domanda. Vedi OBSERVATION_CHARTER.md righe 122-125.
QUOTA_GIORNI_NO_NEWS = 0.60
BANDA_PNL_USD = 200.0

VARIANTI = (
    ("A", "non-decidibili -> THIN_NEUTRAL", THIN_NEUTRAL),
    ("B", "non-decidibili -> OFF_TOPIC", OFF_TOPIC),
    ("C", "non-decidibili esclusi dal denominatore", None),
)


def carica_giorni() -> list[tuple[str, list[dict]]]:
    """(giorno, candidati_miss) per ogni dossier, in ordine di data."""
    giorni = []
    for path in sorted(DOSSIER_DIR.glob("*.json")):
        dossier = json.loads(path.read_text())
        giorni.append((path.stem, dossier.get("candidati_miss") or []))
    return giorni


def rimappa(candidati: list[dict], destinazione: str | None) -> list[dict]:
    """Applica una variante ai candidati di un giorno.

    `destinazione is None` = variante C: i non-decidibili NON vengono riscritti
    in un altro bucket, vengono tolti. E' la differenza sostanziale fra «non so»
    e «assumo»: nelle varianti A e B il giorno si giudica su tutti i candidati,
    in C sui soli candidati su cui la domanda ha risposta.
    """
    out = []
    for c in candidati:
        causa = c.get("causa")
        if causa == OFF_TOPIC_NON_DECIDIBILE:
            if destinazione is None:
                continue
            c = {**c, "causa": destinazione}
        out.append(c)
    return out


def pnl_s4_finale() -> tuple[str | None, float | None]:
    """Ultimo P&L economico cumulato di S4 nella finestra. (giorno, valore)."""
    if not PNL_FILE.exists():
        return None, None
    serie = (json.loads(PNL_FILE.read_text())
             .get("pnl_economico", {}).get("cumulato", {}).get("S4", {}))
    if not serie:
        return None, None
    ultimo = sorted(serie)[-1]
    return ultimo, float(serie[ultimo])


def valuta_variante(giorni: list[tuple[str, list[dict]]], destinazione: str | None,
                    verbose: bool) -> dict:
    dominanti: dict[str, str | None] = {}
    for giorno, candidati in giorni:
        rimappati = rimappa(candidati, destinazione)
        dominanti[giorno] = dominant_cause(count_by_cause(rimappati))
        if verbose:
            conteggi = count_by_cause(rimappati)
            print(f"      {giorno}  dominante={dominanti[giorno] or 'PAREGGIO':<26} {conteggi}")

    n_giorni = len(dominanti)
    n_no_news = sum(1 for d in dominanti.values() if d == "NO_NEWS")
    n_pareggi = sum(1 for d in dominanti.values() if d is None)
    quota = n_no_news / n_giorni if n_giorni else 0.0
    return {
        "n_giorni": n_giorni,
        "n_no_news": n_no_news,
        "n_pareggi": n_pareggi,
        "quota_no_news": quota,
        "gamba_no_news": quota >= QUOTA_GIORNI_NO_NEWS,
        "dominanti": dominanti,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true",
                    help="stampa la dominante e i conteggi giorno per giorno")
    args = ap.parse_args()

    giorni = carica_giorni()
    if not giorni:
        raise SystemExit(f"Nessun dossier in {DOSSIER_DIR}")

    giorno_pnl, pnl = pnl_s4_finale()
    gamba_pnl = pnl is not None and abs(pnl) <= BANDA_PNL_USD

    print("Sensitivity della domanda di uscita n.1 ai non-decidibili (#244)")
    print("=" * 78)
    print(f"Finestra: {giorni[0][0]} .. {giorni[-1][0]}  ({len(giorni)} sedute con dossier)")
    print("Falsificazione pre-registrata (carta, riga 122-125):")
    print(f"  gamba 1  NO_NEWS dominante in >= {QUOTA_GIORNI_NO_NEWS:.0%} dei giorni")
    print(f"  gamba 2  P&L economico S4 dentro +/- ${BANDA_PNL_USD:.0f}")
    print("  le due gambe sono in AND: entrambe vere => «non esiste alpha»")
    print()

    # --- inventario dei non-decidibili -------------------------------------
    tot = sum(len(c) for _, c in giorni)
    n_nd = sum(1 for _, cs in giorni for c in cs
               if c.get("causa") == OFF_TOPIC_NON_DECIDIBILE)
    n_ot = sum(1 for _, cs in giorni for c in cs if c.get("causa") == OFF_TOPIC)
    print(f"Candidati miss totali: {tot}")
    print(f"  OFF_TOPIC (decidibile, ticker assente dal testo): {n_ot}")
    print(f"  OFF_TOPIC_NON_DECIDIBILE (snippet troncato):      {n_nd}"
          f"  ({n_nd / tot:.1%} del totale)" if tot else "")
    print()

    # --- le tre varianti ---------------------------------------------------
    print(f"{'var':4} {'trattamento':42} {'NO_NEWS dom.':>13} {'quota':>7}  gamba 1")
    print("-" * 78)
    esiti = {}
    for sigla, etichetta, destinazione in VARIANTI:
        if args.verbose:
            print(f"  [{sigla}] {etichetta}")
        r = valuta_variante(giorni, destinazione, args.verbose)
        esiti[sigla] = r
        print(f"{sigla:4} {etichetta:42} {r['n_no_news']:5d}/{r['n_giorni']:<7d} "
              f"{r['quota_no_news']:6.1%}  {'VERA' if r['gamba_no_news'] else 'FALSA'}")
    print("-" * 78)

    # --- gamba P&L (invariante alle varianti) ------------------------------
    if pnl is None:
        print("gamba 2 (P&L S4): NON VALUTABILE — economic_pnl.json assente o senza serie S4")
    else:
        print(f"gamba 2 (P&L S4 cumulato al {giorno_pnl}): ${pnl:+,.2f} -> "
              f"{'VERA' if gamba_pnl else 'FALSA'} (banda +/- ${BANDA_PNL_USD:.0f})")
        print("         invariante alle tre varianti: non dipende dalla classificazione.")
    print()

    # --- il verdetto cambia? -----------------------------------------------
    gambe1 = {s: e["gamba_no_news"] for s, e in esiti.items()}
    verdetti = {s: (g1 and bool(gamba_pnl)) for s, g1 in gambe1.items()}
    print("VERDETTO «non esiste alpha nella news editoriale» (gamba1 AND gamba2):")
    for sigla, _, _ in VARIANTI:
        print(f"  variante {sigla}: {'FALSIFICATA (=> no alpha)' if verdetti[sigla] else 'NON falsificata'}")
    print()

    if len(set(verdetti.values())) == 1:
        stabile = next(iter(verdetti.values()))
        print("=> IL VERDETTO NON CAMBIA fra le tre varianti.")
        print(f"   Tutte e tre danno: {'FALSIFICATA' if stabile else 'NON falsificata'}.")
        print("   La conclusione del 28/09 sulla domanda n.1 NON e' ostaggio del")
        print("   trattamento dei non-decidibili: QX-01 (#30) resta necessaria per")
        print("   attribuire correttamente il difetto, ma non per decidere la domanda.")
    else:
        print("=> IL VERDETTO CAMBIA fra le varianti. La domanda n.1 NON e' decidibile")
        print("   senza chiudere il ramo source_metadata: QX-01 (#30) diventa")
        print("   BLOCCANTE per la conclusione del 28/09, non solo per l'attribuzione.")

    # Le quote nude, per il ledger.
    print()
    print("Quote gamba 1 per variante: " + ", ".join(
        f"{s}={esiti[s]['quota_no_news']:.1%}" for s, _, _ in VARIANTI))
    pareggi = ", ".join(f"{s}={esiti[s]['n_pareggi']}" for s, _, _ in VARIANTI)
    print(f"Giorni senza dominante (pareggio) per variante: {pareggi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
