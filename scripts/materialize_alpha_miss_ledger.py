#!/usr/bin/env python3
"""Materializza il ledger alpha-miss dai candidati emessi dalla sessione (#287).

Fino a oggi la sessione Claude appendeva da sola a ``findings.json`` e
``market_daily.jsonl``, con le guardie scritte in prosa nel prompt. Con il
nuovo contratto la sessione emette un file di candidati strutturato e questo
orchestratore decide: verifica il contratto prompt/dossier, valida i
candidati coi moduli puri e scrive SOLO se la validazione passa, atomicamente
(tmp + replace). Un rifiuto lascia i file di evidenza esattamente come sono.

Orchestratore sottile: nessuna regola vive qui, ogni decisione sta in
``src/analysis/dossier/prompt_contract.py`` e ``.../candidates.py``.

Uso (materializzazione, dopo la sessione):
    uv run python scripts/materialize_alpha_miss_ledger.py \
        --dossier docs/evidence/dossier/2026-09-15.json \
        --candidates docs/evidence/candidates/2026-09-15.json \
        --findings docs/evidence/findings.json \
        --market-daily docs/evidence/market_daily.jsonl

Uso (digest Telegram di cinque righe, dopo lo scoreboard):
    uv run python scripts/materialize_alpha_miss_ledger.py --solo-digest \
        --data 2026-09-15 --dossier ... --findings ... --market-daily ... \
        [--economic-pnl docs/evidence/economic_pnl.json]

Ultima riga leggibile a macchina: ``LEDGER_STATUS=`` materializzato |
nessuna_modifica | rifiutato | errore. Exit 0 solo per i primi due.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.analysis.dossier.candidates import applica_candidati, valida_candidati
from src.analysis.dossier.digest import render_digest_telegram
from src.analysis.dossier.prompt_contract import verifica_compatibilita_schema


def _leggi_json(percorso: Path):
    return json.loads(percorso.read_text(encoding="utf-8"))


def _leggi_jsonl(percorso: Path) -> list[dict]:
    righe = []
    for linea in percorso.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            righe.append(json.loads(linea))
    return righe


def _scrivi_json(percorso: Path, payload) -> None:
    tmp = percorso.with_suffix(percorso.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(percorso)  # atomica


def _scrivi_jsonl(percorso: Path, righe: list[dict]) -> None:
    # Le righe vecchie restano byte per byte come le ha scritte il run che le
    # ha prodotte: si riappende soltanto. json.dumps di default, come sempre
    # in questo ledger.
    tmp = percorso.with_suffix(percorso.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for riga in righe:
            fh.write(json.dumps(riga, ensure_ascii=False) + "\n")
    tmp.replace(percorso)  # atomica


def _esiti_findings_del_giorno(findings: dict, data: str) -> list[dict]:
    """I finding applicati quel giorno, nell'ordine del ledger.

    Sono i candidati che il materializzatore (o un run precedente) ha gia'
    accettato: il digest cita solo evidenza materializzata, mai proposte.
    """
    esiti = []
    for record in findings.get("findings") or []:
        for occorrenza in record.get("occorrenze") or []:
            if occorrenza.get("data") == data:
                esiti.append(
                    {
                        "finding_id": record.get("id"),
                        "titolo": record.get("titolo"),
                        "costo_usd": occorrenza.get("costo_usd"),
                    }
                )
                break
    return esiti


def _materializza(args) -> int:
    def rifiuta(messaggi: list[str]) -> int:
        for messaggio in messaggi:
            print(f"RIFIUTO: {messaggio}")
        print("LEDGER_STATUS=rifiutato")
        return 1

    if not args.dossier.exists():
        return rifiuta([f"dossier {args.dossier} non disponibile"])
    dossier = _leggi_json(args.dossier)
    candidati = _leggi_json(args.candidates)
    findings = _leggi_json(args.findings)
    righe = _leggi_jsonl(args.market_daily)

    compatibilita = verifica_compatibilita_schema(dossier)
    if not compatibilita["ok"]:
        return rifiuta(compatibilita["errors"])
    if candidati.get("data") != dossier.get("data"):
        return rifiuta(
            [
                f"data dei candidati {candidati.get('data')!r} diversa da quella "
                f"del dossier {dossier.get('data')!r}"
            ]
        )

    validazione = valida_candidati(candidati, findings, righe_market=righe)
    for avviso in validazione["warnings"]:
        print(f"AVVISO: {avviso}")
    if not validazione["ok"]:
        return rifiuta(validazione["errors"])

    esito = applica_candidati(candidati, findings, righe_market=righe)
    for avviso in esito["warnings"]:
        print(f"AVVISO: {avviso}")

    modificato = False
    if esito["mercato"] == "aggiunta" or esito["applicati"]:
        _scrivi_json(args.findings, esito["findings"])
        _scrivi_jsonl(args.market_daily, esito["righe"])
        modificato = True
    for applicato in esito["applicati"]:
        print(
            f"applicato: {applicato['finding_id']} ({applicato['azione']}, "
            f"mercato: {esito['mercato']})"
        )
    if not modificato:
        print("nessuna modifica da applicare (riga e occorrenze gia' presenti)")
        print("LEDGER_STATUS=nessuna_modifica")
        return 0
    print("LEDGER_STATUS=materializzato")
    return 0


def _digest(args) -> int:
    dossier = _leggi_json(args.dossier) if args.dossier.exists() else {}
    findings = _leggi_json(args.findings) if args.findings.exists() else {}
    righe = _leggi_jsonl(args.market_daily) if args.market_daily.exists() else []
    economico = None
    if args.economic_pnl and args.economic_pnl.exists():
        economico = _leggi_json(args.economic_pnl)

    riga = None
    for r in righe:
        if r.get("data") == args.data:
            riga = r
    esiti = _esiti_findings_del_giorno(findings, args.data)

    for linea in render_digest_telegram(
        dossier, riga, esiti_findings=esiti, scoreboard=economico
    ):
        print(linea)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-digest", action="store_true",
                        help="non materializzare: rendi solo il digest Telegram")
    parser.add_argument("--data", help="seduta del digest (per --solo-digest)")
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--market-daily", type=Path, required=True)
    parser.add_argument("--economic-pnl", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.solo_digest:
            if not args.data:
                parser.error("--solo-digest richiede --data")
            return _digest(args)
        if not args.candidates:
            parser.error("materializzare richiede --candidates")
        return _materializza(args)
    except (OSError, ValueError) as exc:
        print(f"ERRORE: {exc}")
        print("LEDGER_STATUS=errore")
        return 2


if __name__ == "__main__":
    sys.exit(main())