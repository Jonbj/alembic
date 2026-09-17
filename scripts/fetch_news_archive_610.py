#!/usr/bin/env python3
"""Scarica l'archivio news Benzinga 2024-2025 da Alpaca (issue #610).

Scaricatore di **sola lettura verso il sistema**: scrive esclusivamente sotto la
directory di destinazione passata a `--out`. Zero scritture su `news_log`,
`sentiment_signals`, `news_resolved_entities` o Redis.

Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md`
(finestra, universo, popolazioni e regola di abort dichiarati prima di questo
primo download).

## Cosa scrive

Un file JSONL per mese piu' un manifest:

    <out>/news_2024-01.jsonl     una riga per articolo, ESATTAMENTE come Alpaca
                                 lo serve: niente parsing, niente reshaping
    <out>/manifest.json          mesi completati, conteggi, sha256 per file

L'archivio e' grezzo di proposito. La popolazione *ricostruita* — quella che la
pipeline live avrebbe davvero visto — si ottiene applicando a valle i filtri di
produzione importati, mai ricopiati (regola #169/#467). Tenere l'archivio grezzo
e' cio' che rende misurabile la differenza fra le due, che la #610 dichiara
essere essa stessa un risultato.

## Idempotente e ripartibile

L'unita' di lavoro e' il mese. Un mese gia' registrato nel manifest non viene
riscaricato (`--forza` per rifarlo). Ogni mese si scrive su `.part` e si rinomina
solo a scaricamento completo: un'interruzione non lascia mai un mese a meta' che
il run successivo scambierebbe per buono.

Dentro il mese la deduplica e' sull'`id` Alpaca, quindi rieseguire non duplica
righe nemmeno se la paginazione dovesse restituire una pagina due volte.

## Fail-closed — non e' prudenza astratta

Alpaca rifiuta l'**intera** richiesta con `subscription does not permit querying
recent SIP data` quando la finestra tocca l'embargo sul dato recente. Nel pilota
del 2026-09-16 questo ha eliminato **proprio i simboli piu' liquidi** (AAPL,
MSFT, GOOGL, META, NVDA...), portando n da 330 a 68 e **gonfiando l'effetto da
+0,678% a +0,936%**: una finestra troncata non degrada il risultato, lo migliora.

Per questo un fetch fallito **aborta l'intero scaricamento** con exit non-zero e
non promuove nulla: mai proseguire su cio' che resta.

Uso:
    .venv/bin/python scripts/fetch_news_archive_610.py \\
        --out docs/research/2026-09-17-news-archive-610/
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.connectors.alpaca_news import AlpacaNewsConnector  # noqa: E402

# --- parametri congelati dalla pre-registrazione, non rivedibili qui ---
INIZIO = "2024-01-01"
FINE = "2025-12-31"  # il 2026 resta fuori: e' la finestra live gia' osservata
MANIFEST = "manifest.json"


class FetchAbortato(RuntimeError):
    """Un fetch e' fallito: lo scaricamento si ferma senza promuovere nulla."""


def watchlist(config_path: Path) -> list[str]:
    """I 96 simboli di config/trading.yaml, l'universo dichiarato."""
    config = yaml.safe_load(config_path.read_text())
    simboli = list(config["symbols"]["watchlist"])
    if not simboli:
        raise ValueError(f"watchlist vuota in {config_path}")
    return simboli


def mesi(inizio: str, fine: str) -> list[tuple[str, datetime, datetime]]:
    """Finestre mensili [inizio, fine] come (etichetta, da, a) in UTC."""
    primo = datetime.fromisoformat(inizio).replace(tzinfo=timezone.utc)
    ultimo = datetime.fromisoformat(fine).replace(tzinfo=timezone.utc)
    out: list[tuple[str, datetime, datetime]] = []
    anno, mese = primo.year, primo.month
    while (anno, mese) <= (ultimo.year, ultimo.month):
        da = datetime(anno, mese, 1, tzinfo=timezone.utc)
        if mese == 12:
            a = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        else:
            a = datetime(anno, mese + 1, 1, tzinfo=timezone.utc)
        out.append((f"{anno:04d}-{mese:02d}", da, a))
        mese += 1
        if mese == 13:
            anno, mese = anno + 1, 1
    return out


def leggi_manifest(destinazione: Path) -> dict[str, Any]:
    percorso = destinazione / MANIFEST
    if not percorso.exists():
        return {"preregistrazione": "docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md",
                "finestra": {"inizio": INIZIO, "fine": FINE},
                "mesi": {}}
    return json.loads(percorso.read_text())


def scrivi_manifest(destinazione: Path, manifest: dict[str, Any]) -> None:
    percorso = destinazione / MANIFEST
    temporaneo = percorso.with_suffix(".json.part")
    temporaneo.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    temporaneo.replace(percorso)


def sha256_file(percorso: Path) -> str:
    digest = hashlib.sha256()
    with percorso.open("rb") as handle:
        for blocco in iter(lambda: handle.read(1 << 20), b""):
            digest.update(blocco)
    return digest.hexdigest()


async def scarica_mese(
    connettore: AlpacaNewsConnector,
    da: datetime,
    a: datetime,
) -> list[dict]:
    """Articoli grezzi del mese, deduplicati sull'id Alpaca.

    Ogni eccezione risale: e' il chiamante ad abortire, e nessun mese parziale
    viene mai promosso.
    """
    visti: dict[Any, dict] = {}
    async for articolo in connettore.fetch_historical_raw(da, a):
        chiave = articolo.get("id")
        if chiave is None:
            # Un articolo senza id non e' deduplicabile ne' riconciliabile:
            # tenerlo renderebbe il file non riproducibile fra due run.
            raise FetchAbortato(f"articolo senza id nella finestra {da:%Y-%m}")
        visti.setdefault(chiave, articolo)
    return [visti[k] for k in sorted(visti, key=str)]


async def esegui(destinazione: Path, config_path: Path, forza: bool) -> int:
    chiave = os.getenv("ALPACA_API_KEY")
    segreto = os.getenv("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        print("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti", file=sys.stderr)
        return 2

    simboli = watchlist(config_path)
    destinazione.mkdir(parents=True, exist_ok=True)
    manifest = leggi_manifest(destinazione)
    manifest["universo"] = {"n": len(simboli), "simboli": simboli}

    connettore = AlpacaNewsConnector(
        api_key=chiave, api_secret=segreto, symbols=simboli, page_size=50
    )

    for etichetta, da, a in mesi(INIZIO, FINE):
        if etichetta in manifest["mesi"] and not forza:
            print(f"{etichetta}: gia' a terra ({manifest['mesi'][etichetta]['articoli']} articoli)")
            continue

        print(f"{etichetta}: scarico...", flush=True)
        try:
            articoli = await scarica_mese(connettore, da, a)
        except Exception as errore:  # noqa: BLE001 — qualunque fallimento aborta
            print(
                f"ABORT su {etichetta}: {type(errore).__name__}: {errore}\n"
                "Nessun mese parziale e' stato promosso e il manifest non e' stato "
                "aggiornato: una finestra troncata auto-seleziona il campione "
                "(embargo SIP, pilota 2026-09-16) e va corretta, non aggirata.",
                file=sys.stderr,
            )
            return 1

        file_mese = destinazione / f"news_{etichetta}.jsonl"
        parziale = file_mese.with_suffix(".jsonl.part")
        with parziale.open("w", encoding="utf-8") as handle:
            for articolo in articoli:
                handle.write(json.dumps(articolo, ensure_ascii=False, sort_keys=True) + "\n")
        parziale.replace(file_mese)

        manifest["mesi"][etichetta] = {
            "articoli": len(articoli),
            "file": file_mese.name,
            "sha256": sha256_file(file_mese),
            "scaricato_il": datetime.now(timezone.utc).isoformat(),
        }
        scrivi_manifest(destinazione, manifest)
        print(f"{etichetta}: {len(articoli)} articoli")

    totale = sum(m["articoli"] for m in manifest["mesi"].values())
    manifest["totale_articoli"] = totale
    scrivi_manifest(destinazione, manifest)
    print(f"\nArchivio completo: {totale} articoli in {len(manifest['mesi'])} mesi")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="directory di destinazione")
    ap.add_argument("--config", type=Path, default=Path("config/trading.yaml"))
    ap.add_argument("--forza", action="store_true", help="riscarica anche i mesi gia' a terra")
    args = ap.parse_args()
    return asyncio.run(esegui(args.out, args.config, args.forza))


if __name__ == "__main__":
    raise SystemExit(main())
