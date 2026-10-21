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
gruppo, t sulle medie giornaliere, effetto minimo rilevabile a |t|=3, verdetto.

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
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.special import digamma

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.dossier.article_coverage import (  # noqa: E402
    classify_timing,
    content_empty_title_reason,
)

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

# Con meno di 2 giornate l'errore standard fra giornate non e' definito
# (regola INSUFFICIENT_N della casa).
MIN_GIORNI = 2

# Barra |t| per verdetto PASS/FAIL.
SOGLIA_T = 3.0

# Atteso (prereg H-A): non-CONTENT_EMPTY > 1; CONTENT_EMPTY indistinguibile
# dal fondo.
#
# "Indistinguibile" NON vuol dire "rapporto = 1": vuol dire "indistinguibile
# da quanto il rapporto vale quando il mercato NON reagisce a nulla", e quel
# valore non e' 1. Il numeratore ha 4 log-return, il denominatore 23; la std
# campionaria con cosi' pochi gradi di liberta' e' sistematicamente piu'
# piccola di sigma (c(4)=0,921 contro c(23)=0,989), quindi anche su un titolo
# che non registra un tubo il rapporto medio cade a 0,955. Testare contro 1
# fa leggere come FAIL un gruppo genuinamente inerte.
#
# Il riferimento e' quindi la nulla a forma chiusa, valutata sulle finestre
# EFFETTIVAMENTE osservate su ciascun articolo (`null_log_rapporto`), e
# l'osservabile e' l'eccesso in spazio logaritmico: log(ratio) - nulla.
# Esso e' centrato su zero per costruzione quando il mercato non reagisce,
# qualunque sia la copertura di barre, e resta positivo per un picco reale.
RAPPORTO_H0 = 1.0  # solo nel commento sopra: il riferimento vero e' la nulla

ET = ZoneInfo("America/New_York")


# ---------- Tipi ----------


@dataclass
class VolatilityRatio:
    """Esito del calcolo del rapporto di volatilita' per un singolo articolo.

    `ratio = vol_evento / vol_baseline`. None quando non calcolabile (finestre
    mancanti, barre insufficienti). Articoli con ratio=None sono esclusi dal
    test: la mancanza di barre minute SIP non e' un'evidenza, e'
    un buco di copertura.
    """

    articolo_id: str
    ticker: str
    timestamp: datetime
    content_empty: bool
    ratio: float | None
    giorno: str  # YYYY-MM-DD in America/New_York — unita. di inferenza


@dataclass
class StatisticaGiornaliera:
    """Media delle medie giornaliere del rapporto, con t fra giornate.

    Prereg §4: l'unita' di inferenza e' la giornata (America/New_York). Ogni
    giornata pesa uno, qualunque sia il numero di articoli; una giornata con un
    solo articolo e' comunque una giornata. ``effetto_rilevabile_a_t3`` e'
    3 × SE stimato dai dati, non una formula ipotetica.
    """

    media: float
    t: float
    se: float
    n_obs: int
    n_giorni: int

    @property
    def effetto_rilevabile_a_t3(self) -> float:
        return SOGLIA_T * self.se if math.isfinite(self.se) else math.inf


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


def _ritorni_finestra(
    close: pd.Series, finestra_inizio: datetime, n_minuti: int
) -> pd.Series | None:
    """Log-return della finestra [inizio, inizio+n_minuti), None se insufficienti.

    Servono almeno due ritorni: con uno solo `std(ddof=1)` e' NaN, che prima
    passava il filtro ``ratio is not None`` e avvelenava media e SE.
    """
    fine = finestra_inizio + pd.Timedelta(minutes=n_minuti)
    barre = close[(close.index >= finestra_inizio) & (close.index < fine)]
    if len(barre) < 2:
        return None
    log_ret = np.log(barre / barre.shift(1)).dropna()
    return log_ret if len(log_ret) >= 2 else None


def _volatilita_finestra(close: pd.Series, finestra_inizio: datetime, n_minuti: int) -> float | None:
    """Std dei log-return nella finestra [inizio, inizio+n_minuti).

    Restituisce None se la finestra non ha abbastanza barre per una std
    campionaria.
    """
    log_ret = _ritorni_finestra(close, finestra_inizio, n_minuti)
    if log_ret is None:
        return None
    vol = float(log_ret.std(ddof=1))
    return vol if math.isfinite(vol) else None


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

    Sopravvive perche' descrive la grandezza grezza; l'osservabile che finisce
    nell'artefatto e' `calcola_esito` — il rapporto da solo non e' confrontabile
    con 1 (vedi `null_log_rapporto`).
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


# ---------- La nulla del rapporto ----------


def null_log_rapporto(ritorni_evento: int, ritorni_fondo: int) -> float:
    """E[log(s_evento/s_fondo)] quando nessuna notizia muove il prezzo.

    Per una std campionaria (ddof=1) su k ritorni indipendenti,
    ``s^2/sigma^2 ~ chi2_{k-1}/(k-1)``, quindi

        E[log s] = 0.5 * psi((k-1)/2) + 0.5 * log 2 - 0.5 * log(k-1)

    Il termine in psi() e' la correzione per gradi di liberta': e' negativo per
    k piccoli e tende a zero per k grandi. Per la finestra pre-registrata
    (5 barre di evento, 24 di fondo) vale -0.1614: **anche un titolo fermo dà
    un rapporto medio di 0.955**, non di 1.

    Non e' una taratura: e' la proprietà della stima, calcolata e non scelta.
    """
    if ritorni_evento < 2 or ritorni_fondo < 2:
        raise ValueError("servono almeno 2 ritorni per finestra")
    def elog(k: int) -> float:
        return 0.5 * float(digamma((k - 1) / 2.0)) + 0.5 * math.log(2.0) - 0.5 * math.log(k - 1)
    return elog(ritorni_evento) - elog(ritorni_fondo)


@dataclass
class EsitoVolatilita:
    """Esito per un articolo: il rapporto grezzo e il suo eccesso sulla nulla.

    `eccesso_log` e' l'osservabile della misura: log(rapporto) meno la nulla
    delle finestre effettivamente osservate. Vale zero per costruzione quando il
    mercato non reagisce, a qualunque copertura di barre — che e' la definizione
    di "indistinguibile dal fondo" che H-A deve poter pronunciare.

    `rapporto` resta nell'artefatto perche' e' la grandezza che la
    pre-registrazione scrive: 0,955 non e' un difetto del titolo, e' la
    correzione per gradi di liberta'.
    """

    rapporto: float
    eccesso_log: float
    n_ritorni_evento: int
    n_ritorni_fondo: int


def calcola_esito(
    ts: datetime,
    close: pd.Series,
    *,
    finestra_evento: int = MINUTI_EVENTO,
    finestra_baseline: int = MINUTI_BASELINE,
) -> EsitoVolatilita | None:
    """Rapporto di volatilita' ed eccesso sulla nulla delle finestre osservate.

    None quando una delle due finestre non e' calcolabile: un buco di copertura
    non e' un'osservazione (vedi `VolatilityRatio`).
    """
    baseline_inizio = ts - pd.Timedelta(minutes=30)
    ritorni_evento = _ritorni_finestra(close, ts, finestra_evento)
    ritorni_fondo = _ritorni_finestra(close, baseline_inizio, finestra_baseline)
    if ritorni_evento is None or ritorni_fondo is None:
        return None
    rapporto = calcola_rapporto(ts, close, finestra_evento=finestra_evento,
                                finestra_baseline=finestra_baseline)
    if rapporto is None or rapporto <= 0.0:
        return None
    nulla = null_log_rapporto(len(ritorni_evento), len(ritorni_fondo))
    return EsitoVolatilita(
        rapporto=rapporto,
        eccesso_log=math.log(rapporto) - nulla,
        n_ritorni_evento=len(ritorni_evento),
        n_ritorni_fondo=len(ritorni_fondo),
    )


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


# ---------- Statistica per giornata ----------


def media_delle_medie_giornaliere(osservazioni: list[tuple[str, float]]) -> StatisticaGiornaliera:
    """Media delle medie giornaliere e t contro RAPPORTO_H0 sull'SE fra giornate.

    ``osservazioni`` = (giorno, rapporto). Sostituisce la versione
    "cluster-robust" della prima PR, che mediava per articolo ed escludeva i
    giorni singleton dal solo SE: un giorno estremo spostava la media senza
    pesare sull'errore, e t esplodeva (PASS spurio).
    """
    per_giorno: dict[str, list[float]] = defaultdict(list)
    for giorno, valore in osservazioni_valide(osservazioni):
        per_giorno[giorno].append(valore)
    medie = [float(np.mean(v)) for v in per_giorno.values()]
    n_obs = sum(len(v) for v in per_giorno.values())
    n = len(medie)
    if n < MIN_GIORNI:
        media = medie[0] if medie else math.nan
        return StatisticaGiornaliera(media=media, t=math.nan, se=math.inf, n_obs=n_obs, n_giorni=n)
    media = float(np.mean(medie))
    se = float(np.std(medie, ddof=1)) / math.sqrt(n)
    t = (media - RAPPORTO_H0) / se if se > 0 else math.nan
    return StatisticaGiornaliera(media=media, t=t, se=se, n_obs=n_obs, n_giorni=n)


def osservazioni_valide(osservazioni: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Scarta None e non finiti: un buco di copertura non e' un'osservazione."""
    return [
        (giorno, float(v)) for giorno, v in osservazioni
        if v is not None and math.isfinite(float(v))
    ]


# ---------- Il confronto fra i due gruppi (la domanda che H-A fa davvero) ----------


@dataclass
class EsitoConfronto:
    """Verdetto di H-A: il detector separa i due gruppi?

    ``differenza`` = media(non_content_empty) - media(content_empty) sull'eccesso
    in spazio logaritmico, calcolata **sulle giornate in cui entrambi i gruppi
    hanno almeno un'osservazione**.

    Il confronto e' appaiato per giornata perche' e' l'unico modo di separare
    l'effetto del detector da quello del calendario: la volatilita' di fondo
    cambia da titolo a titolo e da giornata a giornata (apertura, stagionalita'),
    e una differenza di medie non appaiate mescolerebbe quegli effetti al
    detector. Sui giorni in cui i due gruppi non compaiono entrambi la
    differenza non e' stimabile — e stimarla comunque sarebbe il difetto.

    ``verdetto``: SEPARA / INDISTINGUIBILE / INSUFFICIENT_N, con
    INSUFFICIENT_N che batte gli altri due (regola #171 della casa).
    """

    differenza: float
    t: float
    se: float
    n_giorni_appaiate: int
    n_giorni_content_empty: int
    n_giorni_non_content_empty: int
    verdetto: str

    @property
    def effetto_rilevabile_a_t3(self) -> float:
        return SOGLIA_T * self.se if math.isfinite(self.se) else math.inf


def _medie_giornaliere(osservazioni: list[tuple[str, float]]) -> dict[str, float]:
    per_giorno: dict[str, list[float]] = defaultdict(list)
    for giorno, valore in osservazioni_valide(osservazioni):
        per_giorno[giorno].append(valore)
    return {g: float(np.mean(v)) for g, v in per_giorno.items()}


def confronto_gruppi(osservazioni: list[tuple[str, str, float]]) -> EsitoConfronto:
    """Confronto appaiato per giornata fra i due gruppi del detector.

    ``osservazioni`` = (gruppo, giorno, eccesso_log). H-A chiede se gli articoli
    che il detector RICONOSCE si comportano come gli altri; e' quindi una
    differenza, non due test separati contro la nulla.
    """
    per_gruppo: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for gruppo, giorno, valore in osservazioni:
        per_gruppo[gruppo].append((giorno, valore))

    medie = {nome: _medie_giornaliere(valli) for nome, valli in per_gruppo.items()}
    giorni_ce = medie.get("content_empty", {})
    giorni_nce = medie.get("non_content_empty", {})
    comune = {
        "n_giorni_content_empty": len(giorni_ce),
        "n_giorni_non_content_empty": len(giorni_nce),
    }
    appaiate = sorted(set(giorni_ce) & set(giorni_nce))
    if len(appaiate) < MIN_GIORNI:
        return EsitoConfronto(
            differenza=math.nan, t=math.nan, se=math.inf,
            n_giorni_appaiate=len(appaiate), verdetto="INSUFFICIENT_N", **comune,
        )

    differenze = [giorni_nce[g] - giorni_ce[g] for g in appaiate]
    differenza = float(np.mean(differenze))
    se = float(np.std(differenze, ddof=1)) / math.sqrt(len(differenze))
    if se == 0.0:
        # Dispersione nulla sulle differenze appaiate: il t e' 0/0 e non
        # definibile. Se anche la differenza media e' esattamente zero i due
        # gruppi coincidono giornata per giornata, e "non separano" e' una
        # constatazione esatta, non una mancanza di potenza — dirlo
        # INSUFFICIENT_N sarebbe falso. Una differenza non nulla a dispersione
        # nulla resta invece INSUFFICIENT_N: un t infinito non autorizza PASS.
        return EsitoConfronto(
            differenza=differenza, t=math.nan, se=se,
            n_giorni_appaiate=len(appaiate),
            verdetto="INDISTINGUIBILE" if differenza == 0.0 else "INSUFFICIENT_N",
            **comune,
        )
    t = differenza / se
    if abs(t) < SOGLIA_T:
        return EsitoConfronto(
            differenza=differenza, t=t, se=se, n_giorni_appaiate=len(appaiate),
            verdetto="INSUFFICIENT_N", **comune,
        )
    return EsitoConfronto(
        differenza=differenza, t=t, se=se, n_giorni_appaiate=len(appaiate),
        verdetto="SEPARA" if differenza > 0 else "INDISTINGUIBILE", **comune,
    )


# ---------- Lettura archivio ----------


def leggi_archivio(directory: Path) -> tuple[list[dict], int]:
    """Legge tutti i `news_YYYY-MM.jsonl` in ordine di mese.

    Righe vuote saltate; righe non-JSON saltate ma CONTATE: il conteggio torna
    al chiamante e finisce nell'artefatto, cosi' un buco nell'archivio si vede.
    """
    out: list[dict] = []
    righe_malformate = 0
    for path in sorted(Path(directory).glob("news_*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    righe_malformate += 1
    if righe_malformate:
        print(f"ATTENZIONE: {righe_malformate} righe non JSON saltate in {directory}",
              file=sys.stderr)
    return out, righe_malformate


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


class MisuraAbortita(RuntimeError):
    """Fetch fallito o finestra nell'embargo: la misura si ferma, non si riduce."""


# Prereg §1.1: Alpaca rifiuta l'intera richiesta SIP se tocca il dato recente, e
# nel pilota questo ha tolto proprio i simboli piu' liquidi. Qui l'archivio e'
# 2024-2025, ma il vincolo resta scritto: nessuna finestra oltre now - 3 giorni.
GIORNI_EMBARGO = 3


class CaricatoreBarreAlpaca:
    """Loader di barre al minuto SIP per ``fetch_minute_bars``, fail-closed.

    Scarica una volta per (simbolo, giorno New York) l'intera giornata, estesa
    compresa, e la tiene in memoria e, se richiesto, su disco: gli articoli
    dello stesso titolo nello stesso giorno non rifanno la richiesta. Qualunque
    errore del fetch solleva ``MisuraAbortita``: un simbolo che cade in silenzio
    seleziona il campione a posteriori (prereg §1.1). Un giorno senza barre e'
    invece un dato (niente scambi), non un errore: il rapporto resta None e
    finisce fra i mancanti dell'artefatto.
    """

    def __init__(self, client, cache_dir: Path | None = None, ora: datetime | None = None):
        self._client = client
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._memoria: dict[tuple[str, str], pd.Series] = {}
        self._taglio = (ora or datetime.now(timezone.utc)) - pd.Timedelta(days=GIORNI_EMBARGO)
        self.richieste = 0

    def __call__(self, symbol: str, start: datetime, end: datetime) -> pd.Series:
        if end > self._taglio:
            raise MisuraAbortita(
                f"finestra {symbol} {end.isoformat()} oltre il taglio d'embargo "
                f"{self._taglio.isoformat()}"
            )
        giorni = sorted({start.astimezone(ET).date(), end.astimezone(ET).date()})
        pezzi = [self._giornata(symbol, g.isoformat()) for g in giorni]
        serie = pd.concat([p for p in pezzi if not p.empty]) if any(
            not p.empty for p in pezzi
        ) else pd.Series(dtype=float)
        if serie.empty:
            return serie
        serie = serie[~serie.index.duplicated()].sort_index()
        return serie[(serie.index >= start) & (serie.index < end)]

    def _giornata(self, symbol: str, giorno: str) -> pd.Series:
        chiave = (symbol, giorno)
        if chiave in self._memoria:
            return self._memoria[chiave]
        percorso = self._cache_dir / symbol / f"{giorno}.csv" if self._cache_dir else None
        if percorso is not None and percorso.exists():
            tabella = pd.read_csv(percorso)
            serie = pd.Series(
                tabella["close"].to_numpy(dtype=float),
                index=pd.to_datetime(tabella["timestamp"], utc=True),
            )
        else:
            serie = self._scarica(symbol, giorno)
            if percorso is not None:
                percorso.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({"timestamp": serie.index.astype(str), "close": serie.to_numpy()}).to_csv(
                    percorso, index=False
                )
        self._memoria[chiave] = serie
        return serie

    def _scarica(self, symbol: str, giorno: str) -> pd.Series:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        inizio = pd.Timestamp(giorno, tz=ET)
        self.richieste += 1
        try:
            risposta = self._client.get_stock_bars(StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=inizio.to_pydatetime(),
                end=(inizio + pd.Timedelta(days=1)).to_pydatetime(),
                feed=DataFeed.SIP,
                adjustment=Adjustment.RAW,
            ))
        except Exception as exc:
            raise MisuraAbortita(f"barre al minuto {symbol} {giorno}: {exc}") from exc
        barre = (getattr(risposta, "data", None) or {}).get(symbol) or []
        if not barre:
            return pd.Series(dtype=float)
        return pd.Series(
            [float(b.close) for b in barre],
            index=pd.DatetimeIndex([pd.Timestamp(b.timestamp).tz_convert("UTC") for b in barre]),
        )


# ---------- Artefatto ----------


def scrivi_artefatto(path: Path, payload: dict) -> None:
    """Scrive il JSON dell'esito. Schema libero, campi richiesti dal pre-reg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


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
        # Giornata di mercato: America/New_York (le news dopo le 20:00 ET
        # cadrebbero nel giorno UTC successivo).
        giorno = ts.astimezone(ET).strftime("%Y-%m-%d")
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
        stat = media_delle_medie_giornaliere(
            [(r.giorno, r.ratio) for r in ratios if filtro(r)]
        )
        out[gruppo] = {
            "n": stat.n_obs,
            "n_giorni": stat.n_giorni,
            "media": stat.media,
            "t": stat.t,
            "effetto_rilevabile_a_t3": stat.effetto_rilevabile_a_t3,
            "verdetto": _verdetto(stat.media, stat.t, stat.effetto_rilevabile_a_t3),
        }

    return {
        "anno": anno,
        "selezionati_esclusi": escludi_selezionati,
        "conteggi_pipeline": counts,
        "n_rapporti_calcolati": len(osservazioni_valide([(r.giorno, r.ratio) for r in ratios])),
        "n_rapporti_mancanti": len(ratios) - len(
            osservazioni_valide([(r.giorno, r.ratio) for r in ratios])
        ),
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
    parser.add_argument("--cache-barre", type=Path, default=None,
                        help="Directory di cache delle barre al minuto (una CSV per simbolo-giorno)")
    parser.add_argument("--senza-barre", action="store_true",
                        help="Prova a secco: nessun fetch, tutti i rapporti None e INSUFFICIENT_N")
    args = parser.parse_args(argv)

    archivio, righe_malformate = leggi_archivio(args.archivio)
    if not archivio:
        print(f"Nessun articolo trovato in {args.archivio}", file=sys.stderr)
        return 2
    per_anno = articoli_per_anno(archivio)

    if args.senza_barre:
        def loader(symbol: str, start: datetime, end: datetime) -> pd.Series:
            return pd.Series(dtype=float)
    else:
        import os

        from alpaca.data.historical import StockHistoricalDataClient

        loader = CaricatoreBarreAlpaca(
            StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]),
            cache_dir=args.cache_barre,
        )

    anni = ["2024", "2025"] if args.anno == "both" else [args.anno]
    for anno in anni:
        articoli_anno = per_anno.per_anno.get(anno, [])
        if not articoli_anno:
            print(f"Anno {anno} vuoto, saltato", file=sys.stderr)
            continue
        for escludi in (False, True):
            suffisso = "_no_selezionati" if escludi else ""
            risultato = _esegui_anno(anno, articoli_anno, loader, escludi_selezionati=escludi)
            risultato["righe_archivio_malformate"] = righe_malformate
            out_path = args.out / f"h_a_{anno}{suffisso}.json"
            scrivi_artefatto(out_path, risultato)
            print(f"Scritto {out_path} ({risultato['n_rapporti_calcolati']} rapporti)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())