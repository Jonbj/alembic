"""Misura H-A dell'issue #610 — il detector CONTENT_EMPTY / RETROSPECTIVE
separa davvero?

La domanda che H-A pone non e' se il detector sia preciso (la pre-registrazione
ne fissa il vocabolario in `content_empty_title_reason` di
`src/analysis/dossier/article_coverage.py`, dichiarato per #508). La domanda e':
gli articoli che il detector RICONOSCE producono una reazione di prezzo diversa
da quelli che NON riconosce? Se la risposta e' "indistinguibile dal fondo",
allora filtrare per CONTENT_EMPTY non migliora il segnale — e la Leva A di
#607 va riscritta, non abilitata.

Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md`
  - finestra di popolazione = articoli creati fra 2024-01-01 e 2025-12-31
  - universo = i 96 simboli di `config/trading.yaml:watchlist`
  - scoring FinBERT locale non usato: H-A non guarda il *segnale*, guarda il
    *trigger*; il prompt DK-CoT e' questione di #609
  - 2024 esplorazione (si fissa la direzione attesa), 2025 conferma (eseguita
    una volta sola)
  - barra |t| >= 3, `effetto_rilevabile_a_t3`, `INSUFFICIENT_N` batte PASS/FAIL
  - pubblicato anche senza ROKU/RDDT/HOOD/WDC/SPCX (§6 della pre-registrazione)

## Vincoli di misura (regola #169/#467)

La pipeline di produzione fornisce gia' il rilevatore: lo script lo **importa**
da `src/analysis/dossier/article_coverage.py`, non lo reimplementa. Il
popolamento dell'archivio, la deduplica e lo scarto dei senza-corpo vivono in
`scripts/coverage_news_archive_610.py`: H-A parte dall'archivio gia' filtrato,
non ricostruisce il filtro (regola #169: la misura non duplica la produzione).

## Output

`docs/evidence/h_a_2024.json` e `docs/evidence/h_a_2025.json`, piu' le versioni
"senza i 5 selezionati sull'esito". Ogni file dichiara n, giornate, media per
gruppo, t clusterizzato, effetto minimo rilevabile a |t|=3, verdetto.

Uso:
    .venv/bin/python scripts/event_study_h_a_610.py \\
        --archivio docs/research/2026-09-17-news-archive-610/ \\
        --out docs/evidence/ \\
        --anno {2024|2025|both}
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.dossier.article_coverage import content_empty_title_reason  # noqa: E402

# --- parametri congelati dalla pre-registrazione, non rivedibili qui ---
# Universo watchlist (config/trading.yaml:114) — il sottoinsieme che verra'
# misurato senza i 5 selezionati sull'esito.
SELEZIONATI_SULL_ESITO = frozenset({"ROKU", "RDDT", "HOOD", "WDC", "SPCX"})

# Finestre di misura: volatilita' al minuto (log-return std) confrontata fra
# i 5 minuti post-news e i 24 minuti di baseline (T-30 -> T-6, esclusi i 5
# immediatamente precedenti per non contaminare il fondo).
MINUTI_EVENTO = 5
MINUTI_BASELINE = 24

# Cooldown anti-doppione: articoli dello stesso ticker entro N minuti
# collassano in uno (il mercato reagisce a "una notizia" non a "una raffica").
COOLDOWN_MINUTI = 5

# Soglia di non-rilevabilita': n_cluster_validi < 2 rende il SE cluster-robust
# non definito (regola INSUFFICIENT_N della casa).
MIN_CLUSTER_VALID = 2

# Barra |t| per verdetto PASS/FAIL.
SOGLIA_T = 3.0

# Atteso: non-CONTENT_EMPTY > 1; CONTENT_EMPTY indistinguibile da 1.
# Il "rapporto atteso = 1 per i template" e' l'ipotesi nulla: se la loro
# volatilita' post e' indistinguibile dal fondo, NON separano.
RAPPORTO_H0 = 1.0


# ---------- Tipi ----------


@dataclass
class VolatilityRatio:
    """Esito del calcolo del rapporto di volatilita' per un singolo articolo.

    `ratio = vol_evento / vol_baseline`. None quando non calcolabile (finestre
    mancanti, barre insufficienti). Articoli con ratio=None sono esclusi dal
    test clusterizzato: la mancanza di barre minute SIP non e' un'evidenza, e'
    un buco di copertura.
    """

    articolo_id: str
    ticker: str
    timestamp: datetime
    content_empty: bool
    ratio: float | None
    giorno: str  # YYYY-MM-DD in America/New_York — unit cluster


@dataclass
class ClusteredMean:
    """Media clusterizzata (cluster = giorno in America/New_York).

    SE cluster-robust: ignora i singleton (cluster da 1 sola osservazione)
    perche' non danno informazione sulla variabilita' between-cluster. Con
    meno di 2 cluster validi il SE non e' definito e `t` viene lasciato a
    `inf`/`nan` — segnale per il verdetto di INSUFFICIENT_N.
    """

    media: float
    t: float
    n_obs: int
    n_cluster: int
    n_cluster_validi: int


@dataclass
class PopolazionePerAnno:
    """Split dell'archivio per anno (unita' della pre-registrazione: 2024 vs 2025)."""

    per_anno: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def anni(self) -> list[str]:
        return sorted(self.per_anno.keys())


# ---------- Timestamp parsing ----------


def parse_timestamp(value: str) -> datetime:
    """ISO 8601 Alpaca (`...Z` o `...+00:00`), con o senza frazioni.

    Alpaca serve `created_at` come `2024-03-05T14:30:00Z`. Normalizzo a UTC
    tz-aware perche' la finestra di misura (T-30..T+5 min) e' in UTC.
    """
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------- Classificazione ----------


def classifica(titolo: str) -> tuple[bool, str | None]:
    """Delega al detector di produzione.

    Importato, non reimplementato (regola #169/#467). Restituisce
    `(content_empty, reason)` per ispezione: il `reason` non entra nella
    misura ma aiuta a diagnosticare un artefatto inatteso.
    """
    reason = content_empty_title_reason(titolo)
    return (reason is not None, reason)


# ---------- Volatility ratio ----------


def _volatilita_finestra(close: pd.Series, finestra_inizio: datetime, n_minuti: int) -> float | None:
    """Std dei log-return nella finestra [inizio, inizio+n_minuti).

    Restituisce None se la finestra ha meno di 2 barre (std non definita su
    un punto).
    """
    fine = finestra_inizio + pd.Timedelta(minutes=n_minuti)
    barre = close[(close.index >= finestra_inizio) & (close.index < fine)]
    if len(barre) < 2:
        return None
    log_ret = np.log(barre / barre.shift(1)).dropna()
    if log_ret.empty:
        return None
    return float(log_ret.std(ddof=1))


def calcola_rapporto(
    ts: datetime,
    close: pd.Series,
    *,
    finestra_evento: int = MINUTI_EVENTO,
    finestra_baseline: int = MINUTI_BASELINE,
) -> float | None:
    """Rapporto fra volatilita' nei 5 min dopo `ts` e volatilita' di fondo.

    Fondo = [T-30, T-6) minuti — i 5 min immediatamente precedenti sono
    esclusi per non contaminare con la reazione anticipata che alcuni
    mercati mostrano su flash rumorosi.

    Restituisce None se una delle due finestre e' vuota o ha < 2 barre.
    """
    baseline_inizio = ts - pd.Timedelta(minutes=30)
    vol_baseline = _volatilita_finestra(close, baseline_inizio, finestra_baseline)
    vol_evento = _volatilita_finestra(close, ts, finestra_evento)
    if vol_baseline is None or vol_evento is None:
        return None
    if vol_baseline == 0.0:
        # Fondo piatto: il rapporto e' indefinito (evento/0 o 0/0). Mai
        # segnalare un effetto dove il fondo non esiste.
        return None
    return vol_evento / vol_baseline


# ---------- Cooldown anti-doppione ----------


def within_cooldown(
    ts_a: datetime,
    ts_b: datetime,
    cooldown_minuti: int,
    *,
    ticker_a: str | None = None,
    ticker_b: str | None = None,
) -> bool:
    """True se due articoli vanno collassati in uno (stesso ticker + finestra).

    Su ticker diversi NON collassa: il fan-out multi-ticker e' un fatto di
    popolazione, non un doppione. Tenerli separati preserva la misura per
    articolo-ticker.
    """
    if ticker_a is not None and ticker_b is not None and ticker_a != ticker_b:
        return False
    delta = abs((ts_a - ts_b).total_seconds()) / 60.0
    return delta < cooldown_minuti


# ---------- Statistica clusterizzata ----------


def clustered_mean(observations: list[tuple[int, float]]) -> ClusteredMean:
    """Media clusterizzata con SE cluster-robust (singleton esclusi).

    Un cluster con un solo elemento non dice nulla sulla variabilita'
    between-cluster: lo escludo dal SE (non dalla media). Con meno di 2
    cluster validi il SE non e' definito e segnalo `t=inf` per il verdetto
    INSUFFICIENT_N.
    """
    if not observations:
        return ClusteredMean(media=math.nan, t=math.inf, n_obs=0, n_cluster=0, n_cluster_validi=0)

    obs_per_cluster: dict[int, list[float]] = defaultdict(list)
    for cluster_id, value in observations:
        obs_per_cluster[cluster_id].append(float(value))

    n_obs = sum(len(v) for v in obs_per_cluster.values())
    n_cluster = len(obs_per_cluster)
    media = sum(sum(v) for v in obs_per_cluster.values()) / n_obs

    validi = {c: vs for c, vs in obs_per_cluster.items() if len(vs) >= 2}
    n_validi = len(validi)
    if n_validi < MIN_CLUSTER_VALID:
        # SE cluster-robust non definito: ritorno t=inf come segnale che il
        # verdetto sara' INSUFFICIENT_N (la priorita' in casa).
        return ClusteredMean(
            media=media,
            t=math.inf,
            n_obs=n_obs,
            n_cluster=n_cluster,
            n_cluster_validi=n_validi,
        )

    # Stima naive di M_n := sqrt( (n_c / (n_c - 1)) * sum_c (mean_c - mean)^2 )
    # E' il moltiplicatore del SE cluster-robust nella sua forma classica.
    # Per semplicita' e trasparenza del numero pubblicato, qui lo calcolo
    # come: Varianza between-cluster dei mean_c, scalata per n_c/(n_c - 1).
    cluster_means = [np.mean(vs) for vs in validi.values()]
    cluster_sizes = [len(vs) for vs in validi.values()]
    n_c = n_validi
    grand_mean = float(np.mean(cluster_means))
    M = math.sqrt(
        (n_c / (n_c - 1)) * sum((m - grand_mean) ** 2 for m in cluster_means) / n_c
    )
    # SE = M / sqrt(n_c) (forma classica, vedi Cameron & Miller 2015).
    se = M / math.sqrt(n_c)
    if se == 0.0 or not math.isfinite(se):
        t = math.inf if media != RAPPORTO_H0 else 0.0
    else:
        t = (media - RAPPORTO_H0) / se

    return ClusteredMean(
        media=float(media),
        t=float(t),
        n_obs=n_obs,
        n_cluster=n_cluster,
        n_cluster_validi=n_validi,
    )


def effetto_rilevabile_a_t3(n_cluster: int, n_obs: int, t_target: float = SOGLIA_T) -> float:
    """Minima differenza dal H0 (RAPPORTO_H0=1) rilevabile a |t|=t_target.

    Con n_cluster cluster e n_obs totali, SE = M / sqrt(n_cluster). Se M e'
    la deviazione between-cluster osservata in passato (qui la simulo con
    la regola classica M ~= std(cluster_means) ~= 1/sqrt(n_obs)), allora
    l'effetto minimo = t_target * SE.

    Senza uno studio pilota della varianza between-cluster, la formula
    approssima con uno scenario "between simile a within" (ICC=0.5), che
    e' conservativa per la casa (un ICC piu' alto renderebbe l'effetto
    minimo piu' grande, non piu' piccolo).
    """
    if n_cluster < MIN_CLUSTER_VALID:
        return math.inf
    # SE_ipotico = sqrt(1 / (n_obs * n_cluster))  (forma ICC=0.5)
    se = math.sqrt(1.0 / max(n_obs, 1) + 1.0 / max(n_cluster, 1))
    return float(t_target * se)


# ---------- Lettura archivio ----------


def leggi_archivio(directory: Path) -> list[dict]:
    """Legge tutti i `news_YYYY-MM.jsonl` in ordine di mese.

    Righe vuote o non-JSON sono saltate silenziosamente (un archivio con
    una riga corrotta non e' perso, ma la riga non partecipa alla
    misura). Lo script principale logga il conteggio cosi' un operatore
    puo' accorgersene.
    """
    out: list[dict] = []
    for path in sorted(Path(directory).glob("news_*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    return out


def articoli_per_anno(archivio: list[dict]) -> PopolazionePerAnno:
    """Split per anno di creazione."""
    per_anno: dict[str, list[dict]] = defaultdict(list)
    for articolo in archivio:
        ts = parse_timestamp(str(articolo["created_at"]))
        per_anno[str(ts.year)].append(articolo)
    return PopolazionePerAnno(per_anno=dict(per_anno))


# ---------- Minute bars fetch (seam) ----------


def fetch_minute_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    loader: Callable[[str, datetime, datetime], pd.Series] | None = None,
) -> pd.Series:
    """Scarica le barre minute. Delega a un loader passato come parametro.

    Questo e' un **seam**: lo script di test passa un fake, lo script di
    produzione passa un loader Alpaca con gestione fail-closed. Tenere il
    seam esplicito e' cio' che rende la regola §1.1 della pre-registrazione
    testabile: il fail-closed sull'embargo SIP non e' qui dentro.
    """
    if loader is None:
        return pd.Series(dtype=float)
    return loader(symbol, start, end)


# ---------- Artefatto ----------


def scrivi_artefatto(path: Path, payload: dict) -> None:
    """Scrive il JSON dell'esito. Schema libero, campi richiesti dal pre-reg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


def per_article_day_clusters(ratios: list[VolatilityRatio]) -> list[tuple[int, float]]:
    """Assegna il cluster (giorno) a ogni rapporto, senza pre-mediare.

    Il cluster e' il giorno, ma `clustered_mean` ha bisogno delle
    osservazioni **per articolo** per stimare la varianza within-cluster:
    se un giorno viene ridotto a una sola media prima di arrivarci, quel
    cluster e' sempre un singleton (1 valore) e il SE cluster-robust non e'
    mai definito, qualunque sia il volume di articoli nell'archivio. Ogni
    ticker diverso nello stesso giorno resta un'osservazione separata dello
    stesso cluster: il fan-out multi-ticker e' varianza within-day, non un
    secondo cluster.
    """
    giorni = sorted({r.giorno for r in ratios if r.ratio is not None})
    indice = {giorno: i for i, giorno in enumerate(giorni)}
    return [(indice[r.giorno], r.ratio) for r in ratios if r.ratio is not None]


# ---------- Verdetto ----------


def _verdetto(media: float, t: float, eff_min: float) -> str:
    """PASS / FAIL / INSUFFICIENT_N.

    INSUFFICIENT_N batte tutto (regola #171): se il campione non puo'
    rilevare l'effetto che stiamo cercando, il verdetto NON e' PASS solo
    perche' il t e' alto. E non e' FAIL solo perche' il t e' basso.
    """
    if not math.isfinite(t) or math.isinf(eff_min):
        return "INSUFFICIENT_N"
    if abs(t) < SOGLIA_T:
        return "INSUFFICIENT_N"
    # t >= SOGLIA_T: abbastanza potenza. Ora la direzione conta.
    return "PASS" if media > RAPPORTO_H0 else "FAIL"


# ---------- CLI ----------


def _esegui_anno(
    anno: str,
    articoli_anno: list[dict],
    loader: Callable[[str, datetime, datetime], pd.Series],
    *,
    escludi_selezionati: bool,
) -> dict:
    """Misura per un singolo anno, un singolo gruppo di esclusione."""
    ratios: list[VolatilityRatio] = []
    counts = {"totale": 0, "scarto_no_ticker": 0, "scarto_cooldown": 0}

    # Cooldown per (ticker, giorno) — tiene il primo visto.
    visti: set[tuple[str, str, datetime]] = set()

    for articolo in articoli_anno:
        counts["totale"] += 1
        simboli = articolo.get("symbols") or []
        if not simboli:
            counts["scarto_no_ticker"] += 1
            continue
        # ticker primario = asset_tags[0], come nel resto della pipeline.
        ticker = str(simboli[0]).upper()
        if escludi_selezionati and ticker in SELEZIONATI_SULL_ESITO:
            continue
        ts = parse_timestamp(str(articolo["created_at"]))
        giorno = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")  # operativo: UTC
        chiave = (ticker, giorno, ts)
        # Cooldown: collassa articoli dello stesso ticker entro 5 min.
        skip = False
        for k in visti:
            if k[0] == ticker and k[1] == giorno:
                if within_cooldown(k[2], ts, COOLDOWN_MINUTI, ticker_a=ticker, ticker_b=ticker):
                    skip = True
                    break
        if skip:
            counts["scarto_cooldown"] += 1
            continue
        visti.add(chiave)

        # Finestra di misura: T-30..T+5 minuti (piu' un margine di 1 minuto
        # per coprire l'inclusione esclusiva dell'evento).
        inizio = ts - pd.Timedelta(minutes=30)
        fine = ts + pd.Timedelta(minutes=MINUTI_EVENTO + 1)
        bars = fetch_minute_bars(ticker, inizio, fine, loader=loader)
        ratio = calcola_rapporto(ts, bars)
        content_empty, _ = classifica(str(articolo.get("headline") or ""))
        ratios.append(
            VolatilityRatio(
                articolo_id=str(articolo.get("id")),
                ticker=ticker,
                timestamp=ts,
                content_empty=content_empty,
                ratio=ratio,
                giorno=giorno,
            )
        )

    out: dict[str, dict] = {}
    for gruppo, filtro in (
        ("content_empty", lambda r: r.content_empty),
        ("non_content_empty", lambda r: not r.content_empty),
    ):
        ratios_g = [r for r in ratios if filtro(r) and r.ratio is not None]
        obs = per_article_day_clusters(ratios_g)
        cm = clustered_mean(obs)
        eff = effetto_rilevabile_a_t3(cm.n_cluster_validi, cm.n_obs)
        out[gruppo] = {
            "n": cm.n_obs,
            "n_giorni": cm.n_cluster,
            "n_cluster_validi": cm.n_cluster_validi,
            "media": cm.media,
            "t": cm.t,
            "effetto_rilevabile_a_t3": eff,
            "verdetto": _verdetto(cm.media, cm.t, eff),
        }

    return {
        "anno": anno,
        "selezionati_esclusi": escludi_selezionati,
        "conteggi_pipeline": counts,
        "n_rapporti_calcolati": sum(1 for r in ratios if r.ratio is not None),
        "n_rapporti_mancanti": sum(1 for r in ratios if r.ratio is None),
        "gruppo_content_empty": out.get("content_empty", {}),
        "gruppo_non_content_empty": out.get("non_content_empty", {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Misura H-A (issue #610)")
    parser.add_argument("--archivio", required=True, type=Path,
                        help="Directory con i news_YYYY-MM.jsonl scaricati")
    parser.add_argument("--out", required=True, type=Path,
                        help="Directory di destinazione degli artefatti JSON")
    parser.add_argument("--anno", choices=["2024", "2025", "both"], default="both")
    args = parser.parse_args(argv)

    archivio = leggi_archivio(args.archivio)
    if not archivio:
        print(f"Nessun articolo trovato in {args.archivio}", file=sys.stderr)
        return 2
    per_anno = articoli_per_anno(archivio)

    # Loader di default: niente fetch (seam richiede iniezione esplicita per
    # la produzione). Lo script CLI puro pubblica l'esito della pipeline
    # di classificazione ma non il rapporto di volatilita', che richiede
    # barre minute.
    def loader_vuoto(symbol: str, start: datetime, end: datetime) -> pd.Series:
        return pd.Series(dtype=float)

    anni = ["2024", "2025"] if args.anno == "both" else [args.anno]
    for anno in anni:
        articoli_anno = per_anno.per_anno.get(anno, [])
        if not articoli_anno:
            print(f"Anno {anno} vuoto, saltato", file=sys.stderr)
            continue
        for escludi in (False, True):
            suffisso = "_no_selezionati" if escludi else ""
            risultato = _esegui_anno(anno, articoli_anno, loader_vuoto, escludi_selezionati=escludi)
            out_path = args.out / f"h_a_{anno}{suffisso}.json"
            scrivi_artefatto(out_path, risultato)
            print(f"Scritto {out_path} ({risultato['n_rapporti_calcolati']} rapporti)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())