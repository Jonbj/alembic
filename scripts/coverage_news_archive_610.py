#!/usr/bin/env python3
"""Artefatto di copertura dell'archivio news 2024-2025 (issue #610).

**Va pubblicato PRIMA di qualunque esito.** E' il punto 3 della DoD di Fase 1, e
l'ordine non e' formale: serve a rendere visibile un buco di copertura *prima*
che diventi un effetto. Un mese mezzo vuoto o un simbolo assente si legge qui, e
non si scopre dopo, quando somiglia a un risultato.

Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md`

## Le quattro popolazioni, e perche' sono quattro

    archivio          tutti gli articoli serviti da Alpaca per le finestre di fetch
    popolazione       creati dentro 2024-01-01..2025-12-31 (§1.2 della pre-reg:
                      l'API filtra su updated_at, non su created_at)
    senza_corpo       summary e content entrambi vuoti. `_parse_article` del
                      connettore restituisce None: la pipeline live NON li vede
                      affatto. E' cosa diversa dai template CONTENT_EMPTY, che
                      il testo ce l'hanno — confonderli falserebbe H-A
    ricostruita       cio' che la pipeline avrebbe davvero processato: escluso il
                      senza_corpo, deduplicato sulla chiave di produzione e
                      privato degli articoli stantii all'arrivo

La riduzione a popolazione ricostruita usa **codice di produzione importato**, mai
ricopiato (regola #169/#467):

- `compute_dedup_hash` di `src/connectors/deduplicator.py` — la classe
  `Deduplicator` ha bisogno di Redis, ma la *chiave* e' pura ed e' la regola;
- `_is_stale_news` di `src/workers/sentiment.py`, con `now = updated_at`: e' il
  momento in cui Alpaca ha servito (o ri-servito) l'articolo, cioe' quando la
  pipeline lo avrebbe ricevuto. Con questa scelta il filtro riproduce lo scarto
  vero, ed e' anche cio' che in produzione elimina gli evergreen ri-serviti
  scoperti in §1.2: un articolo del 2020 ri-toccato nel 2024 arriva con
  timestamp 2020 e viene scartato come stantio.

`now = updated_at` e' una ricostruzione dichiarata, non un dato: l'archivio non
registra la latenza di consegna reale. Va letta come tale.

Uso:
    .venv/bin/python scripts/coverage_news_archive_610.py \\
        --archivio <dir> --out docs/evidence/copertura_news_610.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_news_archive_610 import (  # noqa: E402
    FINE,
    INIZIO,
    dentro_popolazione,
    watchlist,
)
from src.analysis.dossier.article_coverage import content_empty_title_reason  # noqa: E402
from src.connectors.deduplicator import compute_dedup_hash  # noqa: E402
from src.models.news import NewsItem  # noqa: E402
from src.workers.sentiment import _is_stale_news  # noqa: E402

ET = ZoneInfo("America/New_York")

# Simboli entrati in watchlist PERCHE' producevano segnali forti
# (config/trading.yaml:114). Ogni esito si pubblica anche senza di loro: usarli
# per misurare se le news producono segnale e' circolare.
SELEZIONATI_SULL_ESITO = ("ROKU", "RDDT", "HOOD", "WDC", "SPCX")


def articoli(archivio: Path) -> Iterator[dict]:
    """Ogni articolo dei JSONL mensili, in ordine di mese."""
    for percorso in sorted(archivio.glob("news_*.jsonl")):
        with percorso.open(encoding="utf-8") as handle:
            for riga in handle:
                riga = riga.strip()
                if riga:
                    yield json.loads(riga)


def senza_corpo(articolo: dict) -> bool:
    """Riproduce lo scarto di `_parse_article`: nessun corpo da analizzare."""
    return not (articolo.get("summary") or "").strip() and not (
        articolo.get("content") or ""
    ).strip()


def _come_news_item(articolo: dict) -> NewsItem:
    """L'articolo grezzo nella forma che il codice di produzione accetta."""
    corpo = (articolo.get("content") or "").strip() or (articolo.get("summary") or "").strip()
    return NewsItem(
        id=str(articolo.get("id")),
        title=str(articolo.get("headline") or ""),
        body=corpo,
        timestamp=datetime.fromisoformat(str(articolo["created_at"]).replace("Z", "+00:00")),
        source="alpaca_benzinga",
        asset_tags=list(articolo.get("symbols") or []),
        url=str(articolo.get("url") or ""),
    )


def _fuori_orario(creato: datetime) -> bool:
    """Fuori 09:30-16:00 America/New_York, o nel weekend."""
    locale = creato.astimezone(ET)
    if locale.weekday() >= 5:
        return True
    minuti = locale.hour * 60 + locale.minute
    return not (9 * 60 + 30 <= minuti <= 16 * 60)


def copertura(archivio: Path, universo: list[str]) -> dict[str, Any]:
    conteggi = Counter()
    per_mese: dict[str, Counter] = defaultdict(Counter)
    simboli = Counter()
    hash_visti: set[str] = set()
    hash_duplicati = 0

    for articolo in articoli(archivio):
        conteggi["archivio"] += 1
        if not dentro_popolazione(articolo):
            conteggi["fuori_finestra_created_at"] += 1
            continue

        conteggi["popolazione"] += 1
        creato = datetime.fromisoformat(str(articolo["created_at"]).replace("Z", "+00:00"))
        mese = f"{creato.year:04d}-{creato.month:02d}"
        per_mese[mese]["popolazione"] += 1

        for simbolo in articolo.get("symbols") or []:
            simboli[simbolo] += 1

        if len(articolo.get("symbols") or []) > 1:
            conteggi["multi_ticker"] += 1
            per_mese[mese]["multi_ticker"] += 1
        if _fuori_orario(creato):
            conteggi["fuori_orario"] += 1
            per_mese[mese]["fuori_orario"] += 1
        if content_empty_title_reason(articolo.get("headline")):
            conteggi["template_content_empty"] += 1
            per_mese[mese]["template_content_empty"] += 1

        if senza_corpo(articolo):
            conteggi["senza_corpo"] += 1
            per_mese[mese]["senza_corpo"] += 1
            continue  # la pipeline non lo vede affatto: fuori dalla ricostruita

        item = _come_news_item(articolo)
        aggiornato = str(articolo.get("updated_at") or articolo["created_at"])
        arrivo = datetime.fromisoformat(aggiornato.replace("Z", "+00:00"))
        if _is_stale_news(item, now=arrivo):
            conteggi["stantio_all_arrivo"] += 1
            per_mese[mese]["stantio_all_arrivo"] += 1
            continue

        chiave = compute_dedup_hash(item)
        if chiave in hash_visti:
            hash_duplicati += 1
            conteggi["duplicato_produzione"] += 1
            per_mese[mese]["duplicato_produzione"] += 1
            continue
        hash_visti.add(chiave)

        conteggi["ricostruita"] += 1
        per_mese[mese]["ricostruita"] += 1

    # I `symbols` di Benzinga contengono ogni ticker taggato, non solo i 96
    # richiesti: contarli tutti gonfierebbe la copertura di due ordini di
    # grandezza e nasconderebbe proprio il buco che questo artefatto cerca.
    nell_universo = {s: n for s, n in simboli.items() if s in set(universo)}
    return {
        "preregistrazione": "docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md",
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "finestra_popolazione": {"inizio": INIZIO, "fine": FINE, "filtro": "created_at"},
        "nota_ricostruzione": (
            "La popolazione ricostruita usa codice di produzione importato: "
            "compute_dedup_hash e _is_stale_news con now=updated_at. "
            "now=updated_at e' una ricostruzione dichiarata, non un dato: "
            "l'archivio non registra la latenza di consegna reale."
        ),
        "popolazioni": {
            "archivio": conteggi["archivio"],
            "fuori_finestra_created_at": conteggi["fuori_finestra_created_at"],
            "popolazione": conteggi["popolazione"],
            "senza_corpo": conteggi["senza_corpo"],
            "stantio_all_arrivo": conteggi["stantio_all_arrivo"],
            "duplicato_produzione": conteggi["duplicato_produzione"],
            "ricostruita": conteggi["ricostruita"],
        },
        "quote_sulla_popolazione": {
            "senza_corpo": _quota(conteggi["senza_corpo"], conteggi["popolazione"]),
            "multi_ticker": _quota(conteggi["multi_ticker"], conteggi["popolazione"]),
            "fuori_orario": _quota(conteggi["fuori_orario"], conteggi["popolazione"]),
            "template_content_empty": _quota(
                conteggi["template_content_empty"], conteggi["popolazione"]
            ),
        },
        "simboli": {
            "universo_richiesto": len(universo),
            "universo_coperto": len(nell_universo),
            "universo_assente": sorted(set(universo) - set(nell_universo)),
            "universo_sotto_50_articoli": sorted(
                s for s, n in nell_universo.items() if n < 50
            ),
            "primi_20_dell_universo": sorted(
                nell_universo.items(), key=lambda kv: (-kv[1], kv[0])
            )[:20],
            "selezionati_sull_esito": {
                s: nell_universo.get(s, 0) for s in SELEZIONATI_SULL_ESITO
            },
            "tag_distinti_totali": len(simboli),
            "nota_tag": (
                "tag_distinti_totali conta ogni ticker taggato da Benzinga, "
                "compresi quelli fuori watchlist: non e' copertura dell'universo."
            ),
        },
        "per_mese": {
            mese: dict(valori) for mese, valori in sorted(per_mese.items())
        },
    }


def _quota(parte: int, totale: int) -> float | None:
    return round(parte / totale, 6) if totale else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--archivio", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=Path("config/trading.yaml"))
    args = ap.parse_args()

    if not any(args.archivio.glob("news_*.jsonl")):
        print(f"nessun JSONL mensile in {args.archivio}", file=sys.stderr)
        return 1

    risultato = copertura(args.archivio, watchlist(args.config))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(risultato, indent=2, ensure_ascii=False, sort_keys=True))

    pop = risultato["popolazioni"]
    print(f"archivio           {pop['archivio']:>7}")
    print(f"  fuori finestra   {pop['fuori_finestra_created_at']:>7}")
    print(f"popolazione        {pop['popolazione']:>7}")
    print(f"  senza corpo      {pop['senza_corpo']:>7}")
    print(f"  stantio arrivo   {pop['stantio_all_arrivo']:>7}")
    print(f"  duplicato prod.  {pop['duplicato_produzione']:>7}")
    print(f"ricostruita        {pop['ricostruita']:>7}")
    sim = risultato["simboli"]
    print(f"\nuniverso coperto: {sim['universo_coperto']}/{sim['universo_richiesto']}")
    if sim["universo_assente"]:
        print(f"  assenti: {', '.join(sim['universo_assente'])}")
    print(f"artefatto: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
