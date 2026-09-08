#!/usr/bin/env python3
"""Recall del residuo di copertura del calendario earnings (#507 step 5).

Il wiring fix (#533) ha ripristinato la discriminazione True/False di
`giorno_di_earnings`; questa misura risponde all'altra domanda dell'issue: la
fonte FMP vede, il giorno stesso, gli eventi earnings della watchlist che
contano? Campione, verita' ed esito sono pre-registrati in
`docs/evidence/PREREGISTRAZIONE_CALENDARIO_EARNINGS_507.md` — scritta prima
che esistesse una sola seduta post-fix. Questa e' la sua valutatrice, non un
criterio autonomo.

Il flag True non viene ricalcolato (#169): si legge quello che il dossier ha
persistito il giorno stesso (`calendario_earnings.simboli_flaggati`; fallback
sugli intenti per i dossier privi del campo, con il confondo dichiarato che
conta solo i simboli con un intento). Solo la GT-2 interroga FMP, a run
avvenuto — non e' il flag di produzione, e' la verita' letta retrospettivamente.

Run unico, non da cron: si gira una volta, >=14 giorni dopo la fine della
finestra (fine attesa ~2026-10-05, run indicativo ~2026-10-19).

Uso:
    export FMP_API_KEY=...
    python scripts/measure_earnings_calendar_coverage.py \
        --gt1-json docs/evidence/earnings_reazioni_documentate_507.json
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
PERCORSO_PREREGISTRAZIONE = PROJECT_DIR / "docs" / "evidence" / "PREREGISTRAZIONE_CALENDARIO_EARNINGS_507.md"
PERCORSO_EVIDENZA = PROJECT_DIR / "docs" / "evidence" / "earnings_calendar_coverage_507.json"
PERCORSO_GT1 = PROJECT_DIR / "docs" / "evidence" / "earnings_reazioni_documentate_507.json"

# Parametri della pre-registrazione, riportati senza modifiche. Servono a
# rendere eseguibile il protocollo, non a tararlo: cambiarli dopo il run e'
# un secondo esperimento e richiede una nuova pre-registrazione.
N_SEDUTE = 20
MAX_SEDUTE_UNKNOWN = 4
MIN_EVENTI_GT1 = 5
SOGLIA_RECALL = 0.5
DAL = "2026-09-08"  # prima seduta post-#533 attesa


def _watchlist() -> set[str]:
    with open(PROJECT_DIR / "config" / "trading.yaml") as f:
        return {str(s).upper() for s in yaml.safe_load(f)["symbols"]["watchlist"]}


def _finestra(dossier_dir: Path, dal: str, n_sedute: int) -> list[tuple[str, dict]]:
    """Le prime `n_sedute` con dossier post-#533, in ordine di data.

    Post-#533 = blocco `calendario_earnings` presente. La serie dei dossier
    comanda sul calendario di borsa: una seduta senza dossier e' una seduta
    che non e' nella finestra, e la finestra incompleta non decide.
    """
    sedute: list[tuple[str, dict]] = []
    for percorso in sorted(dossier_dir.glob("*.json")):
        if percorso.stem < dal:
            continue
        try:
            payload = json.loads(percorso.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(payload.get("calendario_earnings"), dict):
            continue
        sedute.append((percorso.stem, payload))
        if len(sedute) == n_sedute:
            break
    return sedute


def _simboli_flaggati(payload: dict) -> tuple[set[str] | None, str]:
    """L'insieme dei True persistito dalla produzione per la seduta.

    Ritorna anche la fonte: `blocco` quando c'e' `simboli_flaggati`, `intenti`
    come fallback per i dossier pre-campo (confondo dichiarato: il fallback
    vede solo i simboli che avevano un intento quel giorno).
    """
    blocco = payload.get("calendario_earnings") or {}
    if "simboli_flaggati" in blocco:
        campo = blocco["simboli_flaggati"]
        return (set(campo) if campo is not None else None), "blocco"
    intenti = payload.get("intenti_ingresso_s4") or []
    if intenti:
        marcati = {
            str(riga.get("symbol") or "").upper()
            for riga in intenti
            if riga.get("giorno_di_earnings") is True
        }
        # nessun intento marcabile con fonte cieca: UNKNOWN, non vuoto
        if all(riga.get("giorno_di_earnings") is None for riga in intenti):
            return None, "intenti"
        return marcati, "intenti"
    return None, "intenti"


def _leggi_gt1(percorso: Path) -> list[dict]:
    if not percorso.exists():
        return []
    eventi = json.loads(percorso.read_text())
    if not isinstance(eventi, list):
        raise SystemExit(f"GT-1 malformata in {percorso}: attesa una lista di eventi")
    coppie_viste: set[tuple[str, str]] = set()
    for evento in eventi:
        if not {"seduta", "simbolo", "citazione"} <= set(evento):
            raise SystemExit(
                f"GT-1 malformata in {percorso}: ogni evento vuole "
                f"seduta, simbolo e citazione — ricevuto {sorted(evento)}"
            )
        coppia = (str(evento["seduta"]), str(evento["simbolo"]).upper())
        if coppia in coppie_viste:
            raise SystemExit(
                f"GT-1 malformata in {percorso}: coppia duplicata "
                f"(seduta={coppia[0]}, simbolo={coppia[1]})"
            )
        coppie_viste.add(coppia)
    return eventi


def _verita_fmp(sedute: list[str], watchlist: set[str]) -> dict[str, set[str] | None]:
    """GT-2: record FMP delle sedute, letti a run avvenuto.

    Stessa forma della produzione (`from`/`to` sulla data della seduta), ma
    questa non e' la produzione: e' la verita' retrospettiva che tollera il
    lag di ingestione della fonte. Una seduta con fetch fallito vale None —
    la verita' mancata non e' verita' vuota.
    """
    chiave = os.environ.get("FMP_API_KEY", "")
    verita: dict[str, set[str] | None] = {}
    if not chiave:
        for seduta in sedute:
            verita[seduta] = None
        return verita
    import httpx

    for seduta in sedute:
        try:
            risposta = httpx.get(
                "https://financialmodelingprep.com/stable/earnings-calendar",
                params={"from": seduta, "to": seduta, "apikey": chiave},
                timeout=15.0,
            )
            risposta.raise_for_status()
            righe = risposta.json()
            if not isinstance(righe, list):
                verita[seduta] = None
                continue
            verita[seduta] = {
                str(riga.get("symbol") or "").upper()
                for riga in righe
                if str(riga.get("symbol") or "").upper() in watchlist
            }
        except Exception:  # noqa: BLE001 — la seduta senza verita' e' None
            verita[seduta] = None
    return verita


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dossier-dir", type=Path, default=PROJECT_DIR / "docs" / "evidence" / "dossier")
    parser.add_argument("--gt1-json", type=Path, default=PERCORSO_GT1,
                        help="tabella GT-1 curata: [{seduta, simbolo, citazione}]")
    parser.add_argument("--out", type=Path, default=PERCORSO_EVIDENZA)
    parser.add_argument("--dal", default=DAL, help=f"prima seduta post-#533 (default {DAL})")
    args = parser.parse_args()

    watchlist = _watchlist()
    finestra = _finestra(args.dossier_dir, args.dal, N_SEDUTE)

    esito: dict = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "issue": "#507 (step 5, F-063)",
        "protocollo": "docs/evidence/PREREGISTRAZIONE_CALENDARIO_EARNINGS_507.md",
        "parametri": {
            "n_sedute": N_SEDUTE,
            "max_sedute_unknown": MAX_SEDUTE_UNKNOWN,
            "min_eventi_gt1": MIN_EVENTI_GT1,
            "soglia_recall": SOGLIA_RECALL,
        },
        "motivo": None,
    }

    if len(finestra) < N_SEDUTE:
        esito.update(esito="INSUFFICIENT_N",
                     motivo=f"finestra incompleta: {len(finestra)} dossier post-#533 su {N_SEDUTE}")
        return _scrivi(esito, args.out)

    usabili, cieche = [], []
    per_seduta = []
    for seduta, payload in finestra:
        blocco = payload["calendario_earnings"]
        cieca = str(blocco.get("status") or "").upper() != "OBSERVED"
        (cieche if cieca else usabili).append(seduta)
        flaggati, fonte_flag = _simboli_flaggati(payload)
        per_seduta.append({
            "seduta": seduta,
            "status": blocco.get("status"),
            "flaggati": sorted(flaggati) if flaggati is not None else None,
            "fonte_flag": fonte_flag,
            "nota_fonte_flag": (
                "fallback sugli intenti: vede solo i simboli con un intento nella seduta"
                if fonte_flag == "intenti" else None
            ),
        })

    esito["sedute"] = {
        "prima": finestra[0][0],
        "ultima": finestra[-1][0],
        "usabili": len(usabili),
        "unknown": len(cieche),
    }
    if len(cieche) > MAX_SEDUTE_UNKNOWN:
        esito.update(esito="INSUFFICIENT_N",
                     motivo=f"cecità ricomparsa: {len(cieche)} sedute UNKNOWN su {N_SEDUTE} "
                            f"(max {MAX_SEDUTE_UNKNOWN}) — è il difetto primario, non copertura")
        esito["per_seduta"] = per_seduta
        return _scrivi(esito, args.out)

    # --- GT-1: la primaria, curata e indipendente da FMP --------------------
    gt1_eventi = _leggi_gt1(args.gt1_json)
    in_usabili = [e for e in gt1_eventi if e["seduta"] in usabili]
    fuori_finestra = [e for e in gt1_eventi if e["seduta"] not in dict(finestra)]
    in_cieche = [e for e in gt1_eventi if e["seduta"] in cieche]

    if len(in_usabili) < MIN_EVENTI_GT1:
        esito.update(esito="INSUFFICIENT_N",
                     motivo=f"GT-1 sotto la numerosità minima: {len(in_usabili)} eventi "
                            f"usabili su {MIN_EVENTI_GT1} — «most» non è dicibile")
        esito["gt1"] = {"n_eventi": len(in_usabili), "fuori_finestra": len(fuori_finestra),
                        "in_sedute_cieche": len(in_cieche)}
        return _scrivi(esito, args.out)

    flaggati_per_seduta = {
        voce["seduta"]: set(voce["flaggati"] or [])
        for voce in per_seduta if voce["seduta"] in usabili
    }
    tabella_gt1 = []
    for evento in in_usabili:
        simbolo = str(evento["simbolo"]).upper()
        tabella_gt1.append({
            "seduta": evento["seduta"],
            "simbolo": simbolo,
            "citazione": evento["citazione"],
            "flaggato": simbolo in flaggati_per_seduta.get(evento["seduta"], set()),
        })
    n_flaggati = sum(e["flaggato"] for e in tabella_gt1)
    recall_gt1 = n_flaggati / len(tabella_gt1)
    esito["gt1"] = {
        "n_eventi": len(tabella_gt1),
        "n_flaggati": n_flaggati,
        "recall": recall_gt1,
        "eventi": tabella_gt1,
        "fuori_finestra": len(fuori_finestra),
        "in_sedute_cieche": len(in_cieche),
        "nota": "primaria, curata dai report alpha-miss; vede anche ciò che FMP non ingerisce",
    }

    # --- GT-2: la secondaria, deterministica, dichiaratamente circolare -----
    verita_fmp = _verita_fmp(usabili, watchlist)
    ultimo_record = max(
        (simboli and seduta for seduta, simboli in verita_fmp.items() if simboli),
        default=None,
    )
    tabella_gt2, n_gt2_flaggati = [], 0
    for seduta, verita in verita_fmp.items():
        if not verita:
            continue
        for simbolo in sorted(verita):
            marcabile = simbolo in flaggati_per_seduta.get(seduta, set())
            n_gt2_flaggati += marcabile
            tabella_gt2.append({"seduta": seduta, "simbolo": simbolo, "flaggato": marcabile})
    esito["gt2"] = {
        "verita_per_seduta": {
            seduta: sorted(simboli) if simboli is not None else None
            for seduta, simboli in verita_fmp.items()
        },
        "n_eventi": len(tabella_gt2),
        "n_flaggati": n_gt2_flaggati,
        "recall": (n_gt2_flaggati / len(tabella_gt2)) if tabella_gt2 else None,
        "eventi": tabella_gt2,
        "ultimo_record_disponibile": ultimo_record,
        "nota": (
            "secondaria e circolare per costruzione: misura quanto il fetch same-day "
            "vede di ciò che FMP stesso finisce per sapere; non decide l'esito"
        ),
    }

    esito["esito"] = "INADEGUATA" if recall_gt1 < SOGLIA_RECALL else "ADEGUATA"
    esito["motivo"] = (
        f"recall GT-1 {recall_gt1:.0%} (< {SOGLIA_RECALL:.0%}): la fonte manca la maggior "
        "parte degli eventi noti — la #507 resta aperta sulla decisione della fonte"
        if esito["esito"] == "INADEGUATA" else
        f"recall GT-1 {recall_gt1:.0%} (>= {SOGLIA_RECALL:.0%}): la fonte resta, "
        "il residuo è quantificato nella tabella"
    )
    esito["per_seduta"] = per_seduta
    return _scrivi(esito, args.out)


def _scrivi(esito: dict, percorso: Path) -> int:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(esito, indent=2, ensure_ascii=False))
    gt1 = esito.get("gt1") or {}
    dettaglio = esito.get("motivo") or (
        f"recall GT-1 {gt1.get('recall', 0):.0%} "
        f"({gt1.get('n_flaggati', 0)}/{gt1.get('n_eventi', 0)} eventi)"
    )
    print(f"Esito: {esito['esito']} — {dettaglio}. Evidenza: {percorso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
