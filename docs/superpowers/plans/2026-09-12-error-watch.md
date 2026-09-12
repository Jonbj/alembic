# `error_watch` — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leggere i log durevoli dei servizi e dei cron, deduplicare i traceback per fingerprint stabile, e aprire una issue GitHub quando una regola deterministica lo richiede.

**Architecture:** Cinque moduli puri o locali sotto `src/error_watch/` (collector, fingerprint, ledger, gate, reporter) più una CLI sottile in `scripts/error_watch.py` invocata da cron. Solo il reporter scrive all'esterno; tutto il resto gira su log storici in `--dry-run` senza effetti. Stato su file JSONL append-only, nessuna migrazione, nessun container.

**Tech Stack:** Python 3.11, pytest (`asyncio_mode=auto`), PyYAML, `gh` CLI, `src.llm.client.OllamaGLM52Client`, `src.notifications.telegram.TelegramNotifier`.

**Spec:** `docs/superpowers/specs/2026-09-12-error-watch-design.md` — leggila prima di cominciare.

**Convenzioni del repo:**
- Test: `.venv/bin/python -m pytest <path> -v` (in locale `uv run` è rotto — usa `.venv`).
- I messaggi di commit seguono la convenzione del repo (`feat:`/`fix:`/`docs:` + righe di attribuzione in coda, come negli ultimi commit di `git log`).
- Codice e commenti in italiano dove il modulo è nuovo, coerente con `scripts/check_s4_trial_milestones.py`.

---

## Due scostamenti dalla spec, decisi qui

1. **La spec metteva tutta la catena in `scripts/error_watch.py`.** Il piano la spezza in `src/error_watch/*.py` con una CLI sottile. Motivo: `fingerprint` e `gate` devono essere importabili dai test come funzioni pure, e il repo già separa così (`scripts/check_s4_trial_milestones.py` importa da `src/strategies/s4/`).
2. **`config/error_watch.yaml` non dichiara né il modello né un tetto di budget**, che la spec nominava. Il modello è `glm52` fissato in `cliente_predefinito()` — un solo punto da cambiare — e il budget è già governato centralmente da `src/llm/budget.py`: un secondo tetto locale sarebbe un contatore che nessuno riconcilia con quello vero.
3. **La riga 6 della tabella del gate (tappo a 3 aperture/24h) non è un ramo, è un post-filtro.** Presa alla lettera come sesta condizione in ordine non scatterebbe mai, perché le righe 2/3/5 hanno già deciso. Nel codice il tappo si applica *dopo* la decisione, convertendo `APRI`/`APRI_REGRESSIONE` in `DIGEST`.

## Struttura dei file

| File | Responsabilità |
|---|---|
| `src/error_watch/__init__.py` | vuoto, marca il package |
| `src/error_watch/modelli.py` | `Frame`, `EventoGrezzo`, `Stato`, `Decisione`, `BozzaIssue` — solo dati |
| `src/error_watch/fingerprint.py` | normalizzazione del messaggio, frame di attribuzione, hash. **Puro** |
| `src/error_watch/collector.py` | lettura incrementale dei file + parser dei traceback. **Puro salvo l'I/O di lettura** |
| `src/error_watch/ledger.py` | JSONL append-only, ricostruzione dello stato |
| `src/error_watch/gate.py` | decisione `ignora/apri/commenta/apri_regressione/digest`. **Puro** |
| `src/error_watch/reporter.py` | template deterministico, redattore LLM, `gh`, Telegram |
| `src/error_watch/config.py` | caricamento e validazione di `config/error_watch.yaml` |
| `scripts/error_watch.py` | CLI: orchestrazione, `--dry-run`, `--baseline`, heartbeat |
| `scripts/error_watch.sh` | wrapper cron: PATH, lock, log, credenziali Telegram |
| `scripts/run_watched.sh` | wrapper crontab che registra gli exit code in `runs.jsonl` |
| `config/error_watch.yaml` | soglie, superficie critica, LLM, label |
| `tests/error_watch/test_*.py` | unit per ciascun modulo |
| `tests/scripts/test_error_watch_cli.py` | end-to-end in dry-run |

---

### Task 1: Package, modelli dati e configurazione

**Files:**
- Create: `src/error_watch/__init__.py`, `src/error_watch/modelli.py`, `src/error_watch/config.py`, `config/error_watch.yaml`
- Test: `tests/error_watch/__init__.py`, `tests/error_watch/test_config.py`

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# tests/error_watch/test_config.py
from pathlib import Path

import pytest

from src.error_watch.config import Config, carica_config


def test_carica_config_dal_file_di_repo():
    cfg = carica_config(Path("config/error_watch.yaml"))
    assert cfg.occorrenze_non_critiche == 3
    assert cfg.finestra_occorrenze_ore == 24
    assert cfg.giorni_distinti_persistenza == 2
    assert cfg.max_aperture_24h == 3
    assert cfg.commento_dopo_silenzio_giorni == 7
    assert "observability" in cfg.labels
    assert "src/workers/execution.py" in cfg.moduli_critici


def test_config_rifiuta_soglia_non_positiva(tmp_path: Path):
    percorso = tmp_path / "bad.yaml"
    percorso.write_text("soglie:\n  occorrenze_non_critiche: 0\n")
    with pytest.raises(ValueError, match="occorrenze_non_critiche"):
        carica_config(percorso)


def test_config_normalizza_i_moduli_critici_senza_slash_iniziale(tmp_path: Path):
    percorso = tmp_path / "ok.yaml"
    percorso.write_text(
        "superficie_critica:\n"
        "  moduli:\n"
        "    - /src/workers/execution.py\n"
        "    - src/portfolio/\n"
    )
    cfg = carica_config(percorso)
    assert cfg.moduli_critici == ("src/workers/execution.py", "src/portfolio/")
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/error_watch/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.error_watch'`

- [ ] **Step 3: Scrivi i modelli dati**

```python
# src/error_watch/modelli.py
"""Tipi di dato della sorveglianza errori. Nessuna logica, nessun I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


@dataclass(frozen=True)
class Frame:
    """Una riga `File "...", line N, in funzione` di un traceback."""

    file: str
    funzione: str
    linea: int


@dataclass(frozen=True)
class EventoGrezzo:
    """Un traceback estratto da un file di log, prima di ogni deduplicazione."""

    servizio: str
    ts: datetime
    tipo_eccezione: str
    messaggio: str
    frames: tuple[Frame, ...]
    testo: str
    file_log: str
    riga_log: int


@dataclass
class Stato:
    """Stato corrente di un fingerprint, ricostruito dal ledger."""

    fingerprint: str
    servizio: str
    tipo_eccezione: str
    attribuzione: str
    primo_visto: datetime
    ultimo_visto: datetime
    conteggio: int = 0
    occorrenze: list[datetime] = field(default_factory=list)
    giorni_distinti: set[str] = field(default_factory=set)
    messaggi_visti: set[str] = field(default_factory=set)
    silenziato: bool = False
    issue: int | None = None
    issue_chiusa: bool = False
    conteggio_ultimo_avviso: int = 0
    ultimo_avviso: datetime | None = None

    @property
    def ultimo_intervallo(self) -> timedelta:
        """Distanza fra le due occorrenze più recenti (0 se ce n'è una sola)."""
        if len(self.occorrenze) < 2:
            return timedelta(0)
        ordinati = sorted(self.occorrenze)
        return ordinati[-1] - ordinati[-2]


class Decisione(str, Enum):
    IGNORA = "ignora"
    APRI = "apri"
    COMMENTA = "commenta"
    APRI_REGRESSIONE = "apri_regressione"
    DIGEST = "digest"


@dataclass(frozen=True)
class BozzaIssue:
    titolo: str
    corpo: str
    labels: tuple[str, ...]
    redatta_da: str  # "llm" oppure "template"
```

- [ ] **Step 4: Scrivi il caricatore di configurazione**

```python
# src/error_watch/config.py
"""Caricamento e validazione di config/error_watch.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PERCORSO_DEFAULT = Path("config/error_watch.yaml")


@dataclass(frozen=True)
class Config:
    stato_dir: Path
    servizi_dir: Path
    cron_log_dir: Path
    moduli_critici: tuple[str, ...]
    servizi_critici_senza_frame: tuple[str, ...]
    occorrenze_non_critiche: int
    finestra_occorrenze_ore: int
    giorni_distinti_persistenza: int
    max_aperture_24h: int
    commento_dopo_silenzio_giorni: int
    heartbeat_eta_massima_minuti: int
    llm_abilitato: bool
    llm_timeout_secondi: int
    labels: tuple[str, ...]
    repo: str | None


def _positivo(valore: int, nome: str) -> int:
    if valore <= 0:
        raise ValueError(f"{nome} deve essere positivo, ricevuto {valore}")
    return valore


def _normalizza_modulo(voce: str) -> str:
    return voce.strip().lstrip("/")


def carica_config(percorso: Path = PERCORSO_DEFAULT) -> Config:
    dati = yaml.safe_load(percorso.read_text()) or {}
    sorgenti = dati.get("sorgenti", {})
    critica = dati.get("superficie_critica", {})
    soglie = dati.get("soglie", {})
    heartbeat = dati.get("heartbeat", {})
    llm = dati.get("llm", {})
    issue = dati.get("issue", {})
    return Config(
        stato_dir=Path(dati.get("stato_dir", "logs/error_watch")),
        servizi_dir=Path(sorgenti.get("servizi_dir", "logs/containers")),
        cron_log_dir=Path(sorgenti.get("cron_log_dir", "logs")),
        moduli_critici=tuple(_normalizza_modulo(m) for m in critica.get("moduli", [])),
        servizi_critici_senza_frame=tuple(critica.get("servizi_senza_frame", [])),
        occorrenze_non_critiche=_positivo(
            soglie.get("occorrenze_non_critiche", 3), "occorrenze_non_critiche"
        ),
        finestra_occorrenze_ore=_positivo(
            soglie.get("finestra_occorrenze_ore", 24), "finestra_occorrenze_ore"
        ),
        giorni_distinti_persistenza=_positivo(
            soglie.get("giorni_distinti_persistenza", 2), "giorni_distinti_persistenza"
        ),
        max_aperture_24h=_positivo(soglie.get("max_aperture_24h", 3), "max_aperture_24h"),
        commento_dopo_silenzio_giorni=_positivo(
            soglie.get("commento_dopo_silenzio_giorni", 7), "commento_dopo_silenzio_giorni"
        ),
        heartbeat_eta_massima_minuti=_positivo(
            heartbeat.get("eta_massima_minuti", 90), "eta_massima_minuti"
        ),
        llm_abilitato=bool(llm.get("abilitato", True)),
        llm_timeout_secondi=_positivo(llm.get("timeout_secondi", 90), "timeout_secondi"),
        labels=tuple(issue.get("labels", ["observability", "freeze-ok", "needs-triage"])),
        repo=issue.get("repo"),
    )
```

- [ ] **Step 5: Scrivi il file di configurazione**

```yaml
# config/error_watch.yaml
# Sorveglianza degli errori di esecuzione.
# Spec: docs/superpowers/specs/2026-09-12-error-watch-design.md
#
# Strumentazione pura: nessuna soglia di strategia, peso o flag di trading.
# Freeze-ok sotto docs/evidence/OBSERVATION_CHARTER.md (#171).

stato_dir: logs/error_watch

sorgenti:
  servizi_dir: logs/containers
  cron_log_dir: logs

# Superficie critica: fingerprint nuovo qui => issue alla PRIMA occorrenza.
# Definita sul modulo dell'ultimo frame del repo, non sul servizio: execution e
# portfolio_scheduler sono moduli che girano dentro il servizio `worker`, e
# marcare critico tutto cio' che passa da `worker` renderebbe la regola inutile.
superficie_critica:
  moduli:
    - src/workers/execution.py
    - src/workers/portfolio_scheduler.py
    - src/workers/sentiment.py
    - src/workers/news_stream.py
    - src/portfolio/
  # Ripiego quando il traceback non ha alcun frame nostro (crash di avvio, OOM,
  # errore dentro una libreria): allora decide il servizio.
  servizi_senza_frame:
    - beat
    - worker-inference

soglie:
  occorrenze_non_critiche: 3
  finestra_occorrenze_ore: 24
  giorni_distinti_persistenza: 2
  max_aperture_24h: 3
  commento_dopo_silenzio_giorni: 7

heartbeat:
  eta_massima_minuti: 90

llm:
  abilitato: true
  timeout_secondi: 90

issue:
  labels:
    - observability
    - freeze-ok
    - needs-triage
  # null => lo deduce `gh` dal remote del clone.
  repo: null
```

- [ ] **Step 6: Crea i file vuoti di package**

```bash
touch src/error_watch/__init__.py tests/error_watch/__init__.py
```

- [ ] **Step 7: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_config.py -v`
Expected: PASS, 3 test

- [ ] **Step 8: Commit**

```bash
git add src/error_watch config/error_watch.yaml tests/error_watch
git commit -m "feat(error-watch): modelli dati e configurazione"
```

---

### Task 2: Normalizzazione del messaggio d'eccezione

**Files:**
- Create: `src/error_watch/fingerprint.py`
- Test: `tests/error_watch/test_fingerprint.py`

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# tests/error_watch/test_fingerprint.py
from src.error_watch.fingerprint import normalizza_messaggio


def test_ticker_diversi_collassano():
    assert normalizza_messaggio("'NVDA'") == normalizza_messaggio("'TXN'")


def test_numeri_collassano():
    assert normalizza_messaggio("timeout dopo 90s") == normalizza_messaggio("timeout dopo 12s")


def test_uuid_collassa():
    a = "task d4156ba9-4148-4e14-90d4-7a9ca815a43a fallita"
    b = "task 2ed24993-166b-461c-a568-08f6f2a51da0 fallita"
    assert normalizza_messaggio(a) == normalizza_messaggio(b)


def test_timestamp_collassa():
    a = "nessun dato per 2026-09-11 00:00:01"
    b = "nessun dato per 2026-09-12 13:44:09"
    assert normalizza_messaggio(a) == normalizza_messaggio(b)


def test_path_assoluto_collassa_ma_la_forma_resta():
    normalizzato = normalizza_messaggio("non trovo /app/docs/evidence/dossier/2026-09-11.json")
    assert "<path>" in normalizzato
    assert "non trovo" in normalizzato


def test_url_collassa_prima_del_path():
    normalizzato = normalizza_messaggio("GET https://stream.data.alpaca.markets/v1beta1/news")
    assert normalizzato == "GET <url>"


def test_messaggi_realmente_diversi_restano_diversi():
    assert normalizza_messaggio("connection limit exceeded") != normalizza_messaggio(
        "auth failed"
    )


def test_spazi_ridondanti_normalizzati():
    assert normalizza_messaggio("  a   b  ") == "a b"
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: FAIL con `ImportError: cannot import name 'normalizza_messaggio'`

- [ ] **Step 3: Implementa la normalizzazione**

```python
# src/error_watch/fingerprint.py
"""Chiave stabile di un traceback. Funzioni pure: nessun I/O, nessuno stato.

Tre scelte portano il peso del modulo:

1. L'attribuzione usa l'ultimo frame DEL REPO, non l'ultimo frame in assoluto:
   un KeyError che esplode dentro asyncpg ma nasce in portfolio_scheduler e'
   nostro.
2. La chiave usa `file:funzione`, mai `file:linea`. Con la linea dentro, ogni
   refactor ribattezza vecchi errori come nuovi e il ledger perde la memoria
   proprio quando serve: al ritorno di un difetto gia' corretto.
3. Il messaggio viene normalizzato prima dell'hash, cosi' `KeyError: 'NVDA'` e
   `KeyError: 'TXN'` collassano su una riga sola.
"""

from __future__ import annotations

import hashlib
import re

from src.error_watch.modelli import Frame

# L'ordine conta: un UUID contiene cifre, un timestamp pure, e un URL contiene
# quello che sembra un path. Chi sostituisce per primo vince.
_SOSTITUZIONI: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
        "<uuid>",
    ),
    (
        re.compile(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
        ),
        "<ts>",
    ),
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "<data>"),
    (re.compile(r"\bhttps?://\S+"), "<url>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"(?<![\w/])/(?:[\w.-]+/)+[\w.-]+"), "<path>"),
    # Un token maiuscolo fra apici e' quasi sempre un ticker o una chiave di
    # dizionario: entrambi sono il valore, non il difetto. Effetto collaterale
    # accettato: KeyError: 'CLOSE' e KeyError: 'OPEN' collassano insieme. Per
    # questo il corpo della issue riporta sempre i valori grezzi visti.
    (re.compile(r"'([A-Z][A-Z0-9._]{0,9})'"), "'<simbolo>'"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<n>"),
)


def normalizza_messaggio(messaggio: str) -> str:
    """Sostituisce i valori variabili con segnaposto e compatta gli spazi."""
    testo = messaggio.strip()
    for pattern, sostituto in _SOSTITUZIONI:
        testo = pattern.sub(sostituto, testo)
    return " ".join(testo.split())
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: PASS, 8 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/fingerprint.py tests/error_watch/test_fingerprint.py
git commit -m "feat(error-watch): normalizzazione del messaggio d'eccezione"
```

---

### Task 3: Frame di attribuzione

**Files:**
- Modify: `src/error_watch/fingerprint.py`
- Test: `tests/error_watch/test_fingerprint.py`

- [ ] **Step 1: Aggiungi i test che falliscono**

```python
# tests/error_watch/test_fingerprint.py — in coda
from src.error_watch.fingerprint import frame_di_attribuzione, modulo_relativo
from src.error_watch.modelli import Frame

FRAME_LIB = Frame("/app/.venv/lib/python3.11/site-packages/asyncpg/pool.py", "acquire", 12)
FRAME_REPO = Frame("/app/src/workers/portfolio_scheduler.py", "_size_position", 340)
FRAME_LIB_PROFONDO = Frame(
    "/app/.venv/lib/python3.11/site-packages/asyncpg/protocol.py", "execute", 99
)


def test_attribuzione_preferisce_il_frame_del_repo_anche_se_non_e_ultimo():
    frames = (FRAME_REPO, FRAME_LIB, FRAME_LIB_PROFONDO)
    assert frame_di_attribuzione(frames) == FRAME_REPO


def test_attribuzione_prende_il_repo_piu_profondo_quando_ce_ne_sono_due():
    interno = Frame("/app/src/portfolio/risk_monitor.py", "valuta", 7)
    frames = (FRAME_REPO, interno, FRAME_LIB)
    assert frame_di_attribuzione(frames) == interno


def test_senza_frame_del_repo_ripiega_sullultimo():
    frames = (FRAME_LIB, FRAME_LIB_PROFONDO)
    assert frame_di_attribuzione(frames) == FRAME_LIB_PROFONDO


def test_senza_frame_affatto_restituisce_none():
    assert frame_di_attribuzione(()) is None


def test_modulo_relativo_uguale_da_container_e_da_host():
    da_container = modulo_relativo("/app/src/workers/execution.py")
    da_host = modulo_relativo(
        "/home/stefano/Documents/Projects/Alembic/src/workers/execution.py"
    )
    assert da_container == da_host == "src/workers/execution.py"


def test_modulo_relativo_di_libreria_non_contiene_la_versione_di_python():
    relativo = modulo_relativo(
        "/app/.venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py"
    )
    assert relativo == "alpaca/data/live/websocket.py"
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: FAIL con `ImportError: cannot import name 'frame_di_attribuzione'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/fingerprint.py — in coda

_ESCLUSI = ("/site-packages/", "/dist-packages/", "/.venv/", "/lib/python")


def e_frame_del_repo(percorso: str) -> bool:
    """True se il frame appartiene a codice nostro e non a una dipendenza."""
    normalizzato = percorso.replace("\\", "/")
    if normalizzato.startswith("<"):  # <string>, <frozen importlib...>
        return False
    if any(marcatore in normalizzato for marcatore in _ESCLUSI):
        return False
    return (
        "/src/" in normalizzato
        or "/scripts/" in normalizzato
        or normalizzato.startswith(("src/", "scripts/"))
    )


def modulo_relativo(percorso: str) -> str:
    """Percorso stabile fra container e host, senza versione di Python.

    `/app/src/workers/execution.py` e
    `/home/.../Alembic/src/workers/execution.py` devono dare la stessa stringa,
    altrimenti lo stesso difetto avrebbe due fingerprint a seconda di dove e'
    stato osservato.
    """
    normalizzato = percorso.replace("\\", "/")
    # site-packages prima di /app/: altrimenti resterebbe dentro il percorso la
    # versione di Python, e un upgrade dell'immagine ribattezzerebbe gli errori.
    for marcatore in ("/site-packages/", "/dist-packages/"):
        if marcatore in normalizzato:
            return normalizzato.split(marcatore, 1)[1]
    for segmento in ("/src/", "/scripts/"):
        if segmento in normalizzato:
            coda = normalizzato.split(segmento, 1)[1]
            return f"{segmento.strip('/')}/{coda}"
    if normalizzato.startswith("/app/"):
        return normalizzato[len("/app/") :]
    return normalizzato


def frame_di_attribuzione(frames: tuple[Frame, ...]) -> Frame | None:
    """L'ultimo frame nostro; in mancanza, l'ultimo in assoluto.

    Il ripiego non e' una resa: il traceback del websocket Alpaca del
    2026-09-12 non ha un solo frame nostro, e va comunque attribuito a
    qualcosa di stabile per poter essere deduplicato.
    """
    if not frames:
        return None
    nostri = [frame for frame in frames if e_frame_del_repo(frame.file)]
    return nostri[-1] if nostri else frames[-1]
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: PASS, 14 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/fingerprint.py tests/error_watch/test_fingerprint.py
git commit -m "feat(error-watch): frame di attribuzione e percorso modulo stabile"
```

---

### Task 4: Calcolo del fingerprint

**Files:**
- Modify: `src/error_watch/fingerprint.py`
- Test: `tests/error_watch/test_fingerprint.py`

- [ ] **Step 1: Aggiungi i test che falliscono**

```python
# tests/error_watch/test_fingerprint.py — in coda
from src.error_watch.fingerprint import calcola


def _fp(**override):
    base = dict(
        servizio="worker",
        tipo_eccezione="KeyError",
        frames=(Frame("/app/src/workers/execution.py", "_submit", 100),),
        messaggio="'NVDA'",
    )
    base.update(override)
    return calcola(**base)


def test_fingerprint_stabile_al_variare_del_ticker():
    assert _fp(messaggio="'NVDA'") == _fp(messaggio="'TXN'")


def test_fingerprint_stabile_al_refactor_che_sposta_la_funzione():
    """Spostare una funzione di dieci righe non deve creare un errore 'nuovo'."""
    prima = _fp(frames=(Frame("/app/src/workers/execution.py", "_submit", 100),))
    dopo = _fp(frames=(Frame("/app/src/workers/execution.py", "_submit", 110),))
    assert prima == dopo


def test_fingerprint_cambia_se_cambia_la_funzione():
    assert _fp() != _fp(frames=(Frame("/app/src/workers/execution.py", "_cancel", 100),))


def test_fingerprint_cambia_se_cambia_il_tipo_di_eccezione():
    assert _fp() != _fp(tipo_eccezione="ValueError")


def test_fingerprint_cambia_se_cambia_il_servizio():
    assert _fp() != _fp(servizio="beat")


def test_due_keyerror_da_call_site_diversi_non_collassano():
    a = _fp(frames=(Frame("/app/src/workers/execution.py", "_submit", 100),))
    b = _fp(frames=(Frame("/app/src/workers/sentiment.py", "_score", 20),))
    assert a != b


def test_fingerprint_uguale_da_container_e_da_host():
    container = _fp(frames=(Frame("/app/src/workers/execution.py", "_submit", 100),))
    host = _fp(
        frames=(
            Frame(
                "/home/stefano/Documents/Projects/Alembic/src/workers/execution.py",
                "_submit",
                100,
            ),
        )
    )
    assert container == host


def test_fingerprint_e_corto_e_esadecimale():
    valore = _fp()
    assert len(valore) == 12
    assert all(carattere in "0123456789abcdef" for carattere in valore)
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: FAIL con `ImportError: cannot import name 'calcola'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/fingerprint.py — in coda

SENZA_FRAME = "<nessun-frame>"


def attribuzione(frames: tuple[Frame, ...]) -> str:
    """`modulo:funzione` del frame di attribuzione, o un segnaposto stabile."""
    frame = frame_di_attribuzione(frames)
    if frame is None:
        return SENZA_FRAME
    return f"{modulo_relativo(frame.file)}:{frame.funzione}"


def calcola(
    *,
    servizio: str,
    tipo_eccezione: str,
    frames: tuple[Frame, ...],
    messaggio: str,
) -> str:
    """Chiave a 12 cifre esadecimali che identifica il difetto, non l'occorrenza."""
    grezzo = "|".join(
        (
            servizio,
            tipo_eccezione,
            attribuzione(frames),
            normalizza_messaggio(messaggio),
        )
    )
    return hashlib.sha1(grezzo.encode("utf-8")).hexdigest()[:12]
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_fingerprint.py -v`
Expected: PASS, 22 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/fingerprint.py tests/error_watch/test_fingerprint.py
git commit -m "feat(error-watch): calcolo del fingerprint stabile al refactor"
```

---

### Task 5: Parser dei traceback

**Files:**
- Create: `src/error_watch/collector.py`, `tests/error_watch/fixtures/news_stream_reale.log`
- Test: `tests/error_watch/test_collector.py`

- [ ] **Step 1: Crea la fixture da log reale**

Questo blocco è copiato verbatim da `logs/containers/worker-news-stream-2026-09-12.log` (righe 5–17 al 2026-09-12): è un traceback **senza alcun frame nostro**, che è esattamente il caso che il ripiego dell'attribuzione deve reggere.

```bash
mkdir -p tests/error_watch/fixtures
cat > tests/error_watch/fixtures/news_stream_reale.log <<'LOG'
INFO:alpaca.data.live.websocket:starting data websocket connection
INFO:alpaca.data.live.websocket:connecting to wss://stream.data.alpaca.markets/v1beta1/news
ERROR:alpaca.data.live.websocket:error during websocket communication: connection limit exceeded
Traceback (most recent call last):
  File "/app/.venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py", line 343, in _run_forever
    await self._start_ws()
  File "/app/.venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py", line 135, in _start_ws
    await self._auth()
  File "/app/.venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py", line 126, in _auth
    raise ValueError(msg[0].get("msg", "auth failed"))
ValueError: connection limit exceeded
INFO:alpaca.data.live.websocket:starting data websocket connection
LOG
```

- [ ] **Step 2: Scrivi i test che falliscono**

```python
# tests/error_watch/test_collector.py
from datetime import date, datetime, timezone
from pathlib import Path

from src.error_watch.collector import estrai_eventi

FIXTURES = Path(__file__).parent / "fixtures"
DATA = date(2026, 9, 12)

CELERY = """\
[2026-09-11 00:00:00,001: INFO/MainProcess] Task src.workers.execution.run received
[2026-09-11 00:00:01,478: ERROR/ForkPoolWorker-2] Task src.workers.execution.run raised
Traceback (most recent call last):
  File "/app/src/workers/execution.py", line 100, in run
    submit(order)
KeyError: 'NVDA'
[2026-09-11 00:00:02,000: INFO/MainProcess] Task succeeded
"""

CONCATENATO = """\
Traceback (most recent call last):
  File "/app/src/workers/sentiment.py", line 10, in score
    parse(raw)
ValueError: json non valido

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/app/src/workers/sentiment.py", line 20, in score
    fallback()
RuntimeError: fallback esaurito
"""

TRONCATO = """\
riga innocua
Traceback (most recent call last):
  File "/app/src/workers/execution.py", line 100, in run
"""


def test_estrae_un_evento_da_traceback_celery():
    eventi, incompleto = estrai_eventi(CELERY.splitlines(), servizio="worker", data_file=DATA)
    assert incompleto is None
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo_eccezione == "KeyError"
    assert evento.messaggio == "'NVDA'"
    assert evento.servizio == "worker"
    assert len(evento.frames) == 1
    assert evento.frames[0].funzione == "run"
    assert evento.frames[0].linea == 100


def test_timestamp_preso_dal_prefisso_celery_piu_recente():
    eventi, _ = estrai_eventi(CELERY.splitlines(), servizio="worker", data_file=DATA)
    assert eventi[0].ts == datetime(2026, 9, 11, 0, 0, 1, tzinfo=timezone.utc)


def test_senza_prefisso_il_timestamp_ripiega_su_mezzanotte_del_file():
    righe = FIXTURES.joinpath("news_stream_reale.log").read_text().splitlines()
    eventi, _ = estrai_eventi(righe, servizio="worker-news-stream", data_file=DATA)
    assert eventi[0].ts == datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)


def test_traceback_di_libreria_estratto_lo_stesso():
    righe = FIXTURES.joinpath("news_stream_reale.log").read_text().splitlines()
    eventi, _ = estrai_eventi(righe, servizio="worker-news-stream", data_file=DATA)
    assert len(eventi) == 1
    assert eventi[0].tipo_eccezione == "ValueError"
    assert eventi[0].messaggio == "connection limit exceeded"
    assert len(eventi[0].frames) == 3


def test_eccezione_concatenata_vince_lultima():
    eventi, _ = estrai_eventi(CONCATENATO.splitlines(), servizio="worker", data_file=DATA)
    assert len(eventi) == 1
    assert eventi[0].tipo_eccezione == "RuntimeError"
    assert eventi[0].frames[-1].funzione == "score"
    assert eventi[0].frames[-1].linea == 20


def test_traccia_tagliata_a_meta_segnalata_non_persa():
    """Un traceback spezzato dal confine del chunk va rimandato al giro dopo."""
    eventi, incompleto = estrai_eventi(TRONCATO.splitlines(), servizio="worker", data_file=DATA)
    assert eventi == []
    assert incompleto == 1  # indice della riga "Traceback (most recent call last):"


def test_il_testo_verbatim_e_conservato():
    eventi, _ = estrai_eventi(CELERY.splitlines(), servizio="worker", data_file=DATA)
    assert "Traceback (most recent call last):" in eventi[0].testo
    assert "KeyError: 'NVDA'" in eventi[0].testo


def test_righe_senza_traceback_non_producono_eventi():
    eventi, incompleto = estrai_eventi(
        ["tutto bene", "[2026-09-11 00:00:00,001: INFO/MainProcess] ok"],
        servizio="worker",
        data_file=DATA,
    )
    assert eventi == []
    assert incompleto is None
```

- [ ] **Step 3: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.error_watch.collector'`

- [ ] **Step 4: Implementa il parser**

```python
# src/error_watch/collector.py
"""Lettura incrementale dei log e estrazione dei traceback.

Il parser e' una macchina a stati su righe, non una regex sul file intero: i
log sono append-only e vanno letti a pezzi, quindi un traceback puo' finire a
cavallo di due letture. In quel caso l'indice della riga di inizio viene
restituito al chiamante, che arretra l'offset e lo rilegge intero al giro dopo.
Perdere un traceback perche' e' arrivato a meta' giro sarebbe esattamente il
guasto silenzioso che questo sistema esiste per impedire.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone

from src.error_watch.modelli import EventoGrezzo, Frame

INIZIO_TRACEBACK = "Traceback (most recent call last):"

_CONCATENAZIONI = (
    "During handling of the above exception, another exception occurred:",
    "The above exception was the direct cause of the following exception:",
)

_RE_PREFISSO_CELERY = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+: [A-Z]+/[^\]]*\] ?"
)
_RE_FRAME = re.compile(
    r'^\s+File "(?P<file>[^"]+)", line (?P<linea>\d+), in (?P<funzione>.+?)\s*$'
)
_RE_ECCEZIONE = re.compile(r"^(?P<tipo>[A-Za-z_][\w.]*)(?:: (?P<messaggio>.*))?$")


def _ts_da_riga(riga: str) -> datetime | None:
    match = _RE_PREFISSO_CELERY.match(riga)
    if not match:
        return None
    grezzo = datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S")
    return grezzo.replace(tzinfo=timezone.utc)


def _spoglia_prefisso(riga: str) -> str:
    return _RE_PREFISSO_CELERY.sub("", riga)


def estrai_eventi(
    righe: list[str], *, servizio: str, data_file: date
) -> tuple[list[EventoGrezzo], int | None]:
    """Estrae i traceback completi; restituisce anche l'indice di uno troncato.

    Args:
        righe:      righe complete (senza newline finale) da esaminare.
        servizio:   nome del servizio o del job a cui attribuire gli eventi.
        data_file:  data del file di log, usata quando la riga non ha timestamp.

    Returns:
        (eventi completi, indice della riga di inizio di un traceback troncato
        a fine chunk, oppure None).
    """
    mezzanotte = datetime.combine(data_file, time(0, 0), tzinfo=timezone.utc)
    eventi: list[EventoGrezzo] = []
    ultimo_ts: datetime | None = None
    frames: list[Frame] = []
    testo: list[str] = []
    inizio: int | None = None
    ts_evento: datetime | None = None

    for indice, riga in enumerate(righe):
        ts = _ts_da_riga(riga)
        if ts is not None:
            ultimo_ts = ts
        nuda = _spoglia_prefisso(riga)

        if nuda.rstrip() == INIZIO_TRACEBACK:
            if inizio is None:
                inizio = indice
                ts_evento = ultimo_ts
                testo = [riga.rstrip()]
            else:
                # Eccezione concatenata: la catena e' un solo difetto e vince
                # l'ultimo anello, quello che il chiamante ha davvero visto.
                frames = []
                testo.append(riga.rstrip())
            continue

        if inizio is None:
            continue

        testo.append(riga.rstrip())

        frame = _RE_FRAME.match(nuda)
        if frame is not None:
            frames.append(
                Frame(
                    file=frame.group("file"),
                    funzione=frame.group("funzione"),
                    linea=int(frame.group("linea")),
                )
            )
            continue

        if not nuda.strip() or nuda.startswith((" ", "\t")):
            continue  # riga di codice sorgente, freccia ^^^^, riga vuota

        if nuda.strip() in _CONCATENAZIONI:
            continue

        eccezione = _RE_ECCEZIONE.match(nuda.strip())
        if eccezione is not None and frames:
            eventi.append(
                EventoGrezzo(
                    servizio=servizio,
                    ts=ts_evento or ultimo_ts or mezzanotte,
                    tipo_eccezione=eccezione.group("tipo"),
                    messaggio=(eccezione.group("messaggio") or "").strip(),
                    frames=tuple(frames),
                    testo="\n".join(testo),
                    file_log=f"{servizio}-{data_file.isoformat()}.log",
                    riga_log=inizio + 1,
                )
            )
        frames = []
        testo = []
        inizio = None
        ts_evento = None

    return eventi, inizio
```

- [ ] **Step 5: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: PASS, 8 test

- [ ] **Step 6: Commit**

```bash
git add src/error_watch/collector.py tests/error_watch/test_collector.py tests/error_watch/fixtures
git commit -m "feat(error-watch): parser dei traceback con fixture da log reale"
```

---

### Task 6: Lettura incrementale con offset

**Files:**
- Modify: `src/error_watch/collector.py`
- Test: `tests/error_watch/test_collector.py`

- [ ] **Step 1: Aggiungi i test che falliscono**

```python
# tests/error_watch/test_collector.py — in coda
from src.error_watch.collector import carica_offset, leggi_nuove_righe, salva_offset


def test_legge_tutto_alla_prima_lettura(tmp_path: Path):
    log = tmp_path / "worker-2026-09-12.log"
    log.write_text("a\nb\n")
    righe, offset = leggi_nuove_righe(log, 0)
    assert righe == ["a", "b"]
    assert offset == log.stat().st_size


def test_legge_solo_le_righe_nuove_alla_seconda(tmp_path: Path):
    log = tmp_path / "worker-2026-09-12.log"
    log.write_text("a\n")
    _, offset = leggi_nuove_righe(log, 0)
    log.write_text("a\nb\n")
    righe, nuovo_offset = leggi_nuove_righe(log, offset)
    assert righe == ["b"]
    assert nuovo_offset == log.stat().st_size


def test_riga_parziale_non_consumata(tmp_path: Path):
    """Una riga senza newline e' ancora in scrittura: non va letta a meta'."""
    log = tmp_path / "worker-2026-09-12.log"
    log.write_text("completa\npar")
    righe, offset = leggi_nuove_righe(log, 0)
    assert righe == ["completa"]
    assert offset == len("completa\n")


def test_file_troncato_riparte_da_zero(tmp_path: Path):
    log = tmp_path / "worker-2026-09-12.log"
    log.write_text("aaaaaaaaaa\n")
    _, offset = leggi_nuove_righe(log, 0)
    log.write_text("b\n")  # rotazione: il file e' piu' corto dell'offset
    righe, nuovo_offset = leggi_nuove_righe(log, offset)
    assert righe == ["b"]
    assert nuovo_offset == log.stat().st_size


def test_file_mancante_non_esplode(tmp_path: Path):
    righe, offset = leggi_nuove_righe(tmp_path / "non-esiste.log", 0)
    assert righe == []
    assert offset == 0


def test_offset_persistito_e_riletto(tmp_path: Path):
    percorso = tmp_path / "offsets.json"
    salva_offset(percorso, {"a.log": 12})
    assert carica_offset(percorso) == {"a.log": 12}


def test_offset_illeggibile_riparte_vuoto(tmp_path: Path):
    percorso = tmp_path / "offsets.json"
    percorso.write_text("{ non json")
    assert carica_offset(percorso) == {}


def test_byte_di_conta_anche_i_newline(tmp_path: Path):
    """La CLI arretra l'offset di questa quantita': se sbaglia, o rilegge
    all'infinito lo stesso traceback o se lo perde."""
    from src.error_watch.collector import byte_di

    log = tmp_path / "worker-2026-09-12.log"
    log.write_text("ab\ncd\n")
    righe, offset = leggi_nuove_righe(log, 0)
    assert byte_di(righe) == offset
    assert byte_di(["à"]) == 3  # due byte UTF-8 piu' il newline
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: FAIL con `ImportError: cannot import name 'leggi_nuove_righe'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/collector.py — in coda
import json
from pathlib import Path


def leggi_nuove_righe(percorso: Path, offset: int) -> tuple[list[str], int]:
    """Legge le righe COMPLETE dopo `offset`, restituendo il nuovo offset.

    Una riga senza newline finale e' un record ancora in scrittura: leggerla
    significherebbe classificare mezza eccezione. L'offset si ferma prima.
    Se il file e' piu' corto dell'offset e' stato ruotato o troncato: si
    riparte da zero, meglio rileggere che perdere.
    """
    try:
        dimensione = percorso.stat().st_size
    except OSError:
        return [], offset if offset else 0

    if dimensione < offset:
        offset = 0

    try:
        with percorso.open("rb") as handle:
            handle.seek(offset)
            grezzo = handle.read()
    except OSError:
        return [], offset

    if not grezzo:
        return [], offset

    ultimo_a_capo = grezzo.rfind(b"\n")
    if ultimo_a_capo == -1:
        return [], offset

    consumato = grezzo[: ultimo_a_capo + 1]
    testo = consumato.decode("utf-8", errors="replace")
    return testo.splitlines(), offset + len(consumato)


def byte_di(righe: list[str]) -> int:
    """Byte occupati da queste righe, newline incluso. Serve ad arretrare l'offset."""
    return sum(len(riga.encode("utf-8")) + 1 for riga in righe)


def carica_offset(percorso: Path) -> dict[str, int]:
    try:
        return json.loads(percorso.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def salva_offset(percorso: Path, offsets: dict[str, int]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = percorso.with_suffix(".tmp")
    temporaneo.write_text(json.dumps(offsets, indent=2, sort_keys=True))
    temporaneo.replace(percorso)
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: PASS, 16 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/collector.py tests/error_watch/test_collector.py
git commit -m "feat(error-watch): lettura incrementale con offset e troncamento"
```

---

### Task 7: Ledger append-only

**Files:**
- Create: `src/error_watch/ledger.py`
- Test: `tests/error_watch/test_ledger.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/error_watch/test_ledger.py
from datetime import datetime, timezone
from pathlib import Path

from src.error_watch.ledger import Ledger

ORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.jsonl")


def test_fingerprint_sconosciuto_ha_stato_none(tmp_path: Path):
    assert _ledger(tmp_path).stato("abc123") is None


def test_registra_occorrenza_crea_lo_stato(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.registra_occorrenza(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/workers/execution.py:run",
        messaggio="'NVDA'",
        ts=ORA,
    )
    stato = ledger.stato("abc123")
    assert stato is not None
    assert stato.conteggio == 1
    assert stato.primo_visto == ORA
    assert stato.ultimo_visto == ORA
    assert stato.giorni_distinti == {"2026-09-12"}
    assert stato.messaggi_visti == {"'NVDA'"}


def test_lo_stato_sopravvive_alla_rilettura(tmp_path: Path):
    percorso = tmp_path / "ledger.jsonl"
    primo = Ledger(percorso)
    primo.registra_occorrenza(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/workers/execution.py:run",
        messaggio="'NVDA'",
        ts=ORA,
    )
    secondo = Ledger(percorso)
    assert secondo.stato("abc123").conteggio == 1


def test_giorni_distinti_si_accumulano(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for giorno in (11, 12):
        ledger.registra_occorrenza(
            fingerprint="abc123",
            servizio="worker",
            tipo_eccezione="KeyError",
            attribuzione="src/workers/execution.py:run",
            messaggio="'NVDA'",
            ts=ORA.replace(day=giorno),
        )
    assert ledger.stato("abc123").giorni_distinti == {"2026-09-11", "2026-09-12"}


def test_registra_issue_aperta(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.registra_occorrenza(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/workers/execution.py:run",
        messaggio="'NVDA'",
        ts=ORA,
    )
    ledger.registra_issue("abc123", numero=601, ts=ORA)
    stato = ledger.stato("abc123")
    assert stato.issue == 601
    assert stato.conteggio_ultimo_avviso == 1
    assert stato.ultimo_avviso == ORA


def test_registra_chiusura_e_silenziamento(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.registra_occorrenza(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/workers/execution.py:run",
        messaggio="'NVDA'",
        ts=ORA,
    )
    ledger.registra_issue("abc123", numero=601, ts=ORA)
    ledger.registra_chiusura_issue("abc123", ts=ORA)
    assert ledger.stato("abc123").issue_chiusa is True
    ledger.silenzia("abc123", motivo="rumore noto", ts=ORA)
    assert ledger.stato("abc123").silenziato is True


def test_riga_corrotta_scartata_senza_perdere_il_resto(tmp_path: Path):
    percorso = tmp_path / "ledger.jsonl"
    ledger = Ledger(percorso)
    ledger.registra_occorrenza(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/workers/execution.py:run",
        messaggio="'NVDA'",
        ts=ORA,
    )
    with percorso.open("a") as handle:
        handle.write('{"tipo": "occorrenza", "fing')  # scrittura interrotta
    riletto = Ledger(percorso)
    assert riletto.stato("abc123").conteggio == 1
    assert riletto.righe_scartate == 1


def test_aperture_nella_finestra(tmp_path: Path):
    ledger = _ledger(tmp_path)
    for indice, numero in enumerate((601, 602)):
        fingerprint = f"fp{indice}"
        ledger.registra_occorrenza(
            fingerprint=fingerprint,
            servizio="worker",
            tipo_eccezione="KeyError",
            attribuzione="src/workers/execution.py:run",
            messaggio="x",
            ts=ORA,
        )
        ledger.registra_issue(fingerprint, numero=numero, ts=ORA)
    assert ledger.aperture_da(ORA.replace(hour=0)) == 2
    assert ledger.aperture_da(ORA.replace(day=13)) == 0
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_ledger.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.error_watch.ledger'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/ledger.py
"""Memoria della sorveglianza: JSONL append-only.

Append-only e non riscrittura in place per una ragione operativa precisa: se il
processo muore a meta' giro, un file riscritto resterebbe troncato e il sistema
perderebbe la memoria di quali errori ha gia' segnalato — cioe' ricomincerebbe
ad aprire issue doppie proprio dopo un guasto. Qui l'ultima riga incompleta si
scarta e tutto il resto resta valido.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.error_watch.modelli import Stato

_MAX_OCCORRENZE_RICORDATE = 200


class Ledger:
    def __init__(self, percorso: Path):
        self.percorso = percorso
        self.righe_scartate = 0
        self._stati: dict[str, Stato] = {}
        self._aperture: list[tuple[datetime, int]] = []
        self._carica()

    # ---------------------------------------------------------------- lettura
    def _carica(self) -> None:
        try:
            righe = self.percorso.read_text().splitlines()
        except OSError:
            return
        for riga in righe:
            if not riga.strip():
                continue
            try:
                self._applica(json.loads(riga))
            except (json.JSONDecodeError, KeyError, ValueError):
                self.righe_scartate += 1

    def _applica(self, record: dict) -> None:
        tipo = record["tipo"]
        fingerprint = record["fingerprint"]
        ts = datetime.fromisoformat(record["ts"])
        if tipo == "occorrenza":
            stato = self._stati.get(fingerprint)
            if stato is None:
                stato = Stato(
                    fingerprint=fingerprint,
                    servizio=record["servizio"],
                    tipo_eccezione=record["tipo_eccezione"],
                    attribuzione=record["attribuzione"],
                    primo_visto=ts,
                    ultimo_visto=ts,
                )
                self._stati[fingerprint] = stato
            stato.conteggio += 1
            stato.ultimo_visto = max(stato.ultimo_visto, ts)
            stato.occorrenze.append(ts)
            del stato.occorrenze[:-_MAX_OCCORRENZE_RICORDATE]
            stato.giorni_distinti.add(ts.date().isoformat())
            if record.get("messaggio"):
                stato.messaggi_visti.add(record["messaggio"])
        elif tipo == "issue_aperta":
            stato = self._stati[fingerprint]
            stato.issue = record["numero"]
            stato.issue_chiusa = False
            stato.conteggio_ultimo_avviso = stato.conteggio
            stato.ultimo_avviso = ts
            self._aperture.append((ts, record["numero"]))
        elif tipo == "issue_chiusa":
            self._stati[fingerprint].issue_chiusa = True
        elif tipo == "commento":
            stato = self._stati[fingerprint]
            stato.conteggio_ultimo_avviso = stato.conteggio
            stato.ultimo_avviso = ts
        elif tipo == "silenziato":
            self._stati[fingerprint].silenziato = True

    # --------------------------------------------------------------- query
    def stato(self, fingerprint: str) -> Stato | None:
        return self._stati.get(fingerprint)

    def tutti(self) -> list[Stato]:
        return list(self._stati.values())

    def aperture_da(self, inizio: datetime) -> int:
        return sum(1 for ts, _ in self._aperture if ts >= inizio)

    # ------------------------------------------------------------ scrittura
    def _appendi(self, record: dict) -> None:
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        with self.percorso.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._applica(record)

    def registra_occorrenza(
        self,
        *,
        fingerprint: str,
        servizio: str,
        tipo_eccezione: str,
        attribuzione: str,
        messaggio: str,
        ts: datetime,
    ) -> None:
        self._appendi(
            {
                "tipo": "occorrenza",
                "fingerprint": fingerprint,
                "servizio": servizio,
                "tipo_eccezione": tipo_eccezione,
                "attribuzione": attribuzione,
                "messaggio": messaggio,
                "ts": ts.astimezone(timezone.utc).isoformat(),
            }
        )

    def registra_issue(self, fingerprint: str, *, numero: int, ts: datetime) -> None:
        self._appendi(
            {
                "tipo": "issue_aperta",
                "fingerprint": fingerprint,
                "numero": numero,
                "ts": ts.astimezone(timezone.utc).isoformat(),
            }
        )

    def registra_chiusura_issue(self, fingerprint: str, *, ts: datetime) -> None:
        self._appendi(
            {
                "tipo": "issue_chiusa",
                "fingerprint": fingerprint,
                "ts": ts.astimezone(timezone.utc).isoformat(),
            }
        )

    def registra_commento(self, fingerprint: str, *, ts: datetime) -> None:
        self._appendi(
            {
                "tipo": "commento",
                "fingerprint": fingerprint,
                "ts": ts.astimezone(timezone.utc).isoformat(),
            }
        )

    def silenzia(self, fingerprint: str, *, motivo: str, ts: datetime) -> None:
        self._appendi(
            {
                "tipo": "silenziato",
                "fingerprint": fingerprint,
                "motivo": motivo,
                "ts": ts.astimezone(timezone.utc).isoformat(),
            }
        )
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_ledger.py -v`
Expected: PASS, 8 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/ledger.py tests/error_watch/test_ledger.py
git commit -m "feat(error-watch): ledger append-only con stato ricostruibile"
```

---

### Task 8: Gate — una riga di test per ogni riga della tabella

**Files:**
- Create: `src/error_watch/gate.py`
- Test: `tests/error_watch/test_gate.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/error_watch/test_gate.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.error_watch.config import carica_config
from src.error_watch.gate import Decisione, decidi, e_critico
from src.error_watch.modelli import Stato

ORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
CFG = carica_config(Path("config/error_watch.yaml"))


def _stato(**override) -> Stato:
    base = dict(
        fingerprint="abc123",
        servizio="worker",
        tipo_eccezione="KeyError",
        attribuzione="src/connectors/marketaux.py:fetch",
        primo_visto=ORA,
        ultimo_visto=ORA,
        conteggio=1,
        occorrenze=[ORA],
        giorni_distinti={"2026-09-12"},
    )
    base.update(override)
    return Stato(**base)


# --- riga 1: silenziato -----------------------------------------------------
def test_silenziato_non_produce_mai_nulla():
    stato = _stato(silenziato=True, conteggio=999, occorrenze=[ORA] * 999)
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.IGNORA


# --- riga 2: superficie critica --------------------------------------------
def test_critico_apre_alla_prima_occorrenza():
    stato = _stato(attribuzione="src/workers/execution.py:_submit")
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.APRI


def test_e_critico_riconosce_il_modulo():
    assert e_critico(attribuzione="src/workers/execution.py:_submit", servizio="worker", cfg=CFG)


def test_e_critico_riconosce_un_prefisso_di_cartella():
    assert e_critico(attribuzione="src/portfolio/risk_monitor.py:valuta", servizio="worker", cfg=CFG)


def test_e_critico_ripiega_sul_servizio_senza_frame_nostri():
    assert e_critico(attribuzione="<nessun-frame>", servizio="beat", cfg=CFG)
    assert not e_critico(attribuzione="<nessun-frame>", servizio="api", cfg=CFG)


def test_frame_di_libreria_non_e_critico_solo_perche_gira_in_worker():
    assert not e_critico(
        attribuzione="alpaca/data/live/websocket.py:_auth", servizio="worker", cfg=CFG
    )


# --- riga 3: non critico ----------------------------------------------------
def test_non_critico_sotto_soglia_tace():
    stato = _stato(conteggio=2, occorrenze=[ORA, ORA])
    assert decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.IGNORA


def test_non_critico_apre_a_tre_occorrenze_in_24h():
    stato = _stato(conteggio=3, occorrenze=[ORA - timedelta(hours=3), ORA, ORA])
    assert decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.APRI


def test_tre_occorrenze_troppo_vecchie_non_bastano():
    vecchio = ORA - timedelta(hours=30)
    stato = _stato(
        conteggio=3, occorrenze=[vecchio, vecchio, vecchio], giorni_distinti={"2026-09-11"}
    )
    assert decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.IGNORA


def test_due_giorni_distinti_aprono_anche_con_due_sole_occorrenze():
    """Il raro ma persistente: una volta al giorno per due giorni."""
    stato = _stato(
        conteggio=2,
        occorrenze=[ORA - timedelta(days=1), ORA],
        giorni_distinti={"2026-09-11", "2026-09-12"},
    )
    assert decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.APRI


# --- riga 4: issue gia' aperta ---------------------------------------------
def test_issue_aperta_tace_se_il_conteggio_non_raddoppia():
    stato = _stato(issue=601, conteggio=11, conteggio_ultimo_avviso=10, ultimo_avviso=ORA)
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.IGNORA


def test_issue_aperta_commenta_se_il_conteggio_raddoppia():
    stato = _stato(issue=601, conteggio=20, conteggio_ultimo_avviso=10, ultimo_avviso=ORA)
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.COMMENTA


def test_issue_aperta_commenta_se_riappare_dopo_sette_giorni():
    stato = _stato(
        issue=601,
        conteggio=11,
        conteggio_ultimo_avviso=10,
        ultimo_avviso=ORA - timedelta(days=8),
        occorrenze=[ORA - timedelta(days=8), ORA],
    )
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=0) is Decisione.COMMENTA


# --- riga 5: regressione ----------------------------------------------------
def test_issue_chiusa_che_riappare_e_una_regressione():
    stato = _stato(issue=601, issue_chiusa=True)
    assert (
        decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=0)
        is Decisione.APRI_REGRESSIONE
    )


# --- riga 6: tappo (post-filtro, non ramo) ---------------------------------
def test_tappo_converte_apertura_in_digest():
    stato = _stato(attribuzione="src/workers/execution.py:_submit")
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=3) is Decisione.DIGEST


def test_tappo_converte_anche_la_regressione():
    stato = _stato(issue=601, issue_chiusa=True)
    assert decidi(stato=stato, critico=False, ora=ORA, cfg=CFG, aperture_24h=3) is Decisione.DIGEST


def test_tappo_non_tocca_i_commenti():
    stato = _stato(issue=601, conteggio=20, conteggio_ultimo_avviso=10, ultimo_avviso=ORA)
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=9) is Decisione.COMMENTA


def test_il_silenziamento_batte_anche_il_tappo():
    stato = _stato(silenziato=True)
    assert decidi(stato=stato, critico=True, ora=ORA, cfg=CFG, aperture_24h=9) is Decisione.IGNORA
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_gate.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.error_watch.gate'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/gate.py
"""La decisione: aprire, commentare, tacere. Funzione pura.

Qui sta l'unica cosa che il sistema decide davvero, e per questo non e'
delegata a un LLM: e' codice, leggibile, testato riga per riga contro la
tabella della spec.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.error_watch.config import Config
from src.error_watch.modelli import Decisione, Stato


def e_critico(*, attribuzione: str, servizio: str, cfg: Config) -> bool:
    """Vero se il difetto tocca la superficie critica.

    La criticita' e' definita sul MODULO, con il servizio come ripiego solo
    quando non c'e' alcun frame nostro. Definirla sul servizio soltanto
    marcherebbe critico tutto cio' che passa da `worker`, cioe' quasi tutto.
    """
    modulo = attribuzione.split(":", 1)[0]
    if modulo and modulo != "<nessun-frame>":
        return any(modulo.startswith(critico) for critico in cfg.moduli_critici)
    return servizio in cfg.servizi_critici_senza_frame


def _soglia_raggiunta(stato: Stato, ora: datetime, cfg: Config) -> bool:
    finestra = ora - timedelta(hours=cfg.finestra_occorrenze_ore)
    nella_finestra = sum(1 for ts in stato.occorrenze if ts >= finestra)
    if nella_finestra >= cfg.occorrenze_non_critiche:
        return True
    return len(stato.giorni_distinti) >= cfg.giorni_distinti_persistenza


def _merita_commento(stato: Stato, cfg: Config) -> bool:
    raddoppio = stato.conteggio >= 2 * max(stato.conteggio_ultimo_avviso, 1)
    silenzio = stato.ultimo_intervallo >= timedelta(days=cfg.commento_dopo_silenzio_giorni)
    return raddoppio or silenzio


def decidi(
    *,
    stato: Stato,
    critico: bool,
    ora: datetime,
    cfg: Config,
    aperture_24h: int,
) -> Decisione:
    """Applica la tabella del gate; il tappo e' un post-filtro, non un ramo."""
    if stato.silenziato:
        return Decisione.IGNORA

    if stato.issue_chiusa:
        base = Decisione.APRI_REGRESSIONE
    elif stato.issue is not None:
        base = Decisione.COMMENTA if _merita_commento(stato, cfg) else Decisione.IGNORA
    elif critico:
        base = Decisione.APRI
    elif _soglia_raggiunta(stato, ora, cfg):
        base = Decisione.APRI
    else:
        base = Decisione.IGNORA

    if base in (Decisione.APRI, Decisione.APRI_REGRESSIONE):
        if aperture_24h >= cfg.max_aperture_24h:
            return Decisione.DIGEST
    return base
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_gate.py -v`
Expected: PASS, 18 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/gate.py tests/error_watch/test_gate.py
git commit -m "feat(error-watch): gate deterministico con tappo come post-filtro"
```

---

### Task 9: Redattore deterministico (template)

**Files:**
- Create: `src/error_watch/reporter.py`
- Test: `tests/error_watch/test_reporter_template.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/error_watch/test_reporter_template.py
from datetime import datetime, timezone
from pathlib import Path

from src.error_watch.config import carica_config
from src.error_watch.modelli import EventoGrezzo, Frame, Stato
from src.error_watch.reporter import redigi_template

ORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
CFG = carica_config(Path("config/error_watch.yaml"))

EVENTO = EventoGrezzo(
    servizio="worker",
    ts=ORA,
    tipo_eccezione="KeyError",
    messaggio="'NVDA'",
    frames=(Frame("/app/src/workers/execution.py", "_submit", 100),),
    testo='Traceback (most recent call last):\n  File "/app/src/workers/execution.py", line 100, in _submit\nKeyError: \'NVDA\'',
    file_log="worker-2026-09-12.log",
    riga_log=42,
)

STATO = Stato(
    fingerprint="abc123def456",
    servizio="worker",
    tipo_eccezione="KeyError",
    attribuzione="src/workers/execution.py:_submit",
    primo_visto=ORA,
    ultimo_visto=ORA,
    conteggio=7,
    occorrenze=[ORA],
    giorni_distinti={"2026-09-12"},
    messaggi_visti={"'NVDA'", "'TXN'"},
)


def test_titolo_contiene_eccezione_e_attribuzione():
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert "KeyError" in bozza.titolo
    assert "execution.py" in bozza.titolo


def test_corpo_contiene_il_traceback_verbatim():
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert EVENTO.testo in bozza.corpo


def test_corpo_contiene_fingerprint_e_conteggio():
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert "abc123def456" in bozza.corpo
    assert "7" in bozza.corpo


def test_corpo_elenca_i_valori_grezzi_collassati_dalla_normalizzazione():
    """La normalizzazione collassa 'NVDA' e 'TXN': il corpo deve mostrarli entrambi."""
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert "'NVDA'" in bozza.corpo
    assert "'TXN'" in bozza.corpo


def test_corpo_non_contiene_una_sezione_ipotesi():
    """Il template non diagnostica: senza LLM non c'e' ipotesi da offrire."""
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert "Ipotesi" not in bozza.corpo


def test_labels_prese_dalla_config():
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert bozza.labels == CFG.labels


def test_marcata_come_template():
    bozza = redigi_template(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False)
    assert bozza.redatta_da == "template"


def test_regressione_cita_la_issue_chiusa_nel_titolo():
    stato = Stato(**{**STATO.__dict__, "issue": 601, "issue_chiusa": True})
    bozza = redigi_template(stato=stato, evento=EVENTO, cfg=CFG, regressione=True)
    assert "regressione" in bozza.titolo.lower()
    assert "#601" in bozza.corpo
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_reporter_template.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.error_watch.reporter'`

- [ ] **Step 3: Implementa il template**

```python
# src/error_watch/reporter.py
"""Redazione e apertura delle issue.

Il redattore LLM e' un miglioramento della leggibilita', mai un punto di
fallimento: se l'LLM e' giu', in timeout o restituisce JSON non valido, il
template deterministico prende il suo posto e la issue si apre lo stesso. Un
errore critico che non diventa issue perche' un modello non ha risposto
sarebbe il guasto che questo sistema esiste per impedire.
"""

from __future__ import annotations

from datetime import datetime

from src.error_watch.config import Config
from src.error_watch.modelli import BozzaIssue, EventoGrezzo, Stato


def _intestazione(stato: Stato, evento: EventoGrezzo, regressione: bool) -> str:
    prefisso = "regressione: " if regressione else ""
    modulo = stato.attribuzione.split(":", 1)[0].rsplit("/", 1)[-1]
    funzione = stato.attribuzione.split(":", 1)[-1]
    return f"{prefisso}{evento.tipo_eccezione} in {modulo}:{funzione} ({stato.servizio})"


def corpo_evidenza(stato: Stato, evento: EventoGrezzo, regressione: bool) -> str:
    """La parte verbatim del corpo: solo fatti osservati, nessuna diagnosi."""
    valori = ", ".join(f"`{valore}`" for valore in sorted(stato.messaggi_visti)[:10])
    righe = [
        "## Evidenza",
        "",
        f"- **Fingerprint:** `{stato.fingerprint}`",
        f"- **Servizio:** `{stato.servizio}`",
        f"- **Attribuzione:** `{stato.attribuzione}`",
        f"- **Occorrenze:** {stato.conteggio} "
        f"(prima: {stato.primo_visto.isoformat()}, ultima: {stato.ultimo_visto.isoformat()})",
        f"- **Giorni distinti:** {len(stato.giorni_distinti)}",
        f"- **Sorgente:** `{evento.file_log}` riga {evento.riga_log}",
    ]
    if valori:
        righe.append(f"- **Valori osservati nel messaggio:** {valori}")
    if regressione and stato.issue is not None:
        righe.append(
            f"- **Regressione di #{stato.issue}**: quel fingerprint era stato chiuso "
            "e si e' ripresentato."
        )
    righe += [
        "",
        "### Ultimo traceback, verbatim",
        "",
        "```",
        evento.testo,
        "```",
        "",
        "---",
        "",
        "_Issue aperta automaticamente da `scripts/error_watch.py`. "
        "Spec: `docs/superpowers/specs/2026-09-12-error-watch-design.md`._",
    ]
    return "\n".join(righe)


def redigi_template(
    *, stato: Stato, evento: EventoGrezzo, cfg: Config, regressione: bool
) -> BozzaIssue:
    """Bozza senza LLM: solo evidenza, nessuna ipotesi."""
    return BozzaIssue(
        titolo=_intestazione(stato, evento, regressione),
        corpo=corpo_evidenza(stato, evento, regressione),
        labels=cfg.labels,
        redatta_da="template",
    )
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_reporter_template.py -v`
Expected: PASS, 8 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/reporter.py tests/error_watch/test_reporter_template.py
git commit -m "feat(error-watch): redattore deterministico delle issue"
```

---

### Task 10: Redattore LLM con ripiego sul template

**Files:**
- Modify: `src/error_watch/reporter.py`
- Test: `tests/error_watch/test_reporter_llm.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/error_watch/test_reporter_llm.py
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.error_watch.config import carica_config
from src.error_watch.modelli import EventoGrezzo, Frame, Stato
from src.error_watch.reporter import BozzaLLM, redigi

ORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
CFG = carica_config(Path("config/error_watch.yaml"))

EVENTO = EventoGrezzo(
    servizio="worker",
    ts=ORA,
    tipo_eccezione="KeyError",
    messaggio="'NVDA'",
    frames=(Frame("/app/src/workers/execution.py", "_submit", 100),),
    testo="Traceback (most recent call last):\nKeyError: 'NVDA'",
    file_log="worker-2026-09-12.log",
    riga_log=42,
)
STATO = Stato(
    fingerprint="abc123def456",
    servizio="worker",
    tipo_eccezione="KeyError",
    attribuzione="src/workers/execution.py:_submit",
    primo_visto=ORA,
    ultimo_visto=ORA,
    conteggio=7,
    occorrenze=[ORA],
    giorni_distinti={"2026-09-12"},
    messaggi_visti={"'NVDA'"},
)


class ClienteFinto:
    def __init__(self, risposta=None, eccezione=None):
        self.risposta = risposta
        self.eccezione = eccezione
        self.prompt_ricevuto = None

    async def complete(self, prompt, response_schema):
        self.prompt_ricevuto = prompt
        if self.eccezione is not None:
            raise self.eccezione
        return self.risposta


def test_usa_la_bozza_dellllm_quando_risponde():
    cliente = ClienteFinto(
        risposta=BozzaLLM(titolo="KeyError sul sizing", corpo="## Ipotesi\nchiave assente")
    )
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente)
    )
    assert bozza.titolo == "KeyError sul sizing"
    assert bozza.redatta_da == "llm"


def test_levidenza_verbatim_e_sempre_aggiunta_in_coda_al_corpo_llm():
    """L'LLM puo' sbagliare la diagnosi; l'evidenza non e' negoziabile."""
    cliente = ClienteFinto(risposta=BozzaLLM(titolo="t", corpo="## Ipotesi\nboh"))
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente)
    )
    assert "## Evidenza" in bozza.corpo
    assert EVENTO.testo in bozza.corpo
    assert bozza.corpo.index("## Ipotesi") < bozza.corpo.index("## Evidenza")


def test_timeout_dellllm_ripiega_sul_template():
    cliente = ClienteFinto(eccezione=asyncio.TimeoutError())
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente)
    )
    assert bozza.redatta_da == "template"
    assert EVENTO.testo in bozza.corpo


def test_qualsiasi_eccezione_dellllm_ripiega_sul_template():
    cliente = ClienteFinto(eccezione=RuntimeError("json non valido"))
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente)
    )
    assert bozza.redatta_da == "template"


def test_llm_disabilitato_non_viene_nemmeno_chiamato():
    cliente = ClienteFinto(eccezione=AssertionError("non doveva essere chiamato"))
    cfg = carica_config(Path("config/error_watch.yaml"))
    cfg_off = type(cfg)(**{**cfg.__dict__, "llm_abilitato": False})
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=cfg_off, regressione=False, cliente=cliente)
    )
    assert bozza.redatta_da == "template"
    assert cliente.prompt_ricevuto is None


def test_il_prompt_dice_esplicitamente_che_il_se_e_gia_deciso():
    cliente = ClienteFinto(risposta=BozzaLLM(titolo="t", corpo="c"))
    asyncio.run(redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente))
    assert "non devi decidere se aprirla" in cliente.prompt_ricevuto
    assert EVENTO.testo in cliente.prompt_ricevuto


def test_titolo_troppo_lungo_viene_troncato():
    cliente = ClienteFinto(risposta=BozzaLLM(titolo="x" * 400, corpo="c"))
    bozza = asyncio.run(
        redigi(stato=STATO, evento=EVENTO, cfg=CFG, regressione=False, cliente=cliente)
    )
    assert len(bozza.titolo) <= 120
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_reporter_llm.py -v`
Expected: FAIL con `ImportError: cannot import name 'BozzaLLM'`

- [ ] **Step 3: Implementa il redattore LLM**

```python
# src/error_watch/reporter.py — in coda
import asyncio
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_TITOLO = 120


class BozzaLLM(BaseModel):
    """Schema che il modello deve rispettare. Le label NON sono sue."""

    titolo: str = Field(description="Titolo conciso della issue, max 120 caratteri")
    corpo: str = Field(description="Corpo Markdown con una sezione '## Ipotesi'")


def costruisci_prompt(stato: Stato, evento: EventoGrezzo, sorgente: str) -> str:
    return f"""Sei un ingegnere che documenta un difetto gia' rilevato in un sistema di trading.

La decisione di aprire questa issue e' gia' stata presa da una regola deterministica:
non devi decidere se aprirla, solo scriverla bene.

Vincoli:
- Non inventare cause. Se non sai perche' accade, dillo.
- Il corpo deve contenere una sola sezione, `## Ipotesi`, con la tua lettura del difetto
  e cosa andrebbe guardato per confermarla o smentirla.
- L'evidenza verbatim viene aggiunta automaticamente dopo il tuo testo: non ricopiarla.
- Italiano, tono asciutto, niente formule di cortesia.

Servizio: {stato.servizio}
Eccezione: {evento.tipo_eccezione}: {evento.messaggio}
Attribuzione: {stato.attribuzione}
Occorrenze: {stato.conteggio} fra {stato.primo_visto.isoformat()} e {stato.ultimo_visto.isoformat()}

Traceback:
```
{evento.testo}
```

Sorgente della funzione incriminata:
```python
{sorgente}
```
"""


def _tronca(titolo: str) -> str:
    pulito = " ".join(titolo.split())
    return pulito[:MAX_TITOLO]


async def redigi(
    *,
    stato: Stato,
    evento: EventoGrezzo,
    cfg: Config,
    regressione: bool,
    cliente,
    sorgente: str = "",
) -> BozzaIssue:
    """Bozza LLM con evidenza verbatim in coda; ripiega sul template a ogni guasto."""
    fallback = redigi_template(stato=stato, evento=evento, cfg=cfg, regressione=regressione)
    if not cfg.llm_abilitato or cliente is None:
        return fallback

    prompt = costruisci_prompt(stato, evento, sorgente)
    try:
        bozza = await asyncio.wait_for(
            cliente.complete(prompt, BozzaLLM), timeout=cfg.llm_timeout_secondi
        )
    except Exception as errore:  # timeout, JSON invalido, CLI assente: tutti uguali
        logger.warning("redattore LLM non disponibile (%s): uso il template", errore)
        return fallback

    corpo = f"{bozza.corpo}\n\n{corpo_evidenza(stato, evento, regressione)}"
    return BozzaIssue(
        titolo=_tronca(bozza.titolo),
        corpo=corpo,
        labels=cfg.labels,
        redatta_da="llm",
    )


def cliente_predefinito():
    """Il client Ollama Cloud gia' usato dal resto del sistema (`glm52`)."""
    from src.llm.client import OllamaGLM52Client

    return OllamaGLM52Client()
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_reporter_llm.py -v`
Expected: PASS, 7 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/reporter.py tests/error_watch/test_reporter_llm.py
git commit -m "feat(error-watch): redattore LLM con ripiego deterministico"
```

---

### Task 11: Apertura issue via `gh`

**Files:**
- Modify: `src/error_watch/reporter.py`
- Test: `tests/error_watch/test_gh.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/error_watch/test_gh.py
import subprocess

import pytest

from src.error_watch.modelli import BozzaIssue
from src.error_watch.reporter import GhCli, GhNonDisponibile

BOZZA = BozzaIssue(
    titolo="KeyError in execution.py:_submit (worker)",
    corpo="## Evidenza\n...",
    labels=("observability", "freeze-ok", "needs-triage"),
    redatta_da="template",
)


class EsecutoreFinto:
    def __init__(self, uscita="https://github.com/Jonbj/alembic/issues/601\n", codice=0):
        self.uscita = uscita
        self.codice = codice
        self.chiamate = []

    def __call__(self, comando, input=None):
        self.chiamate.append((comando, input))
        if self.codice != 0:
            raise subprocess.CalledProcessError(self.codice, comando, stderr="errore gh")
        return self.uscita


def test_crea_issue_restituisce_il_numero():
    esecutore = EsecutoreFinto()
    numero = GhCli(esecutore=esecutore).crea_issue(BOZZA)
    assert numero == 601


def test_crea_issue_passa_titolo_label_e_corpo_su_stdin():
    esecutore = EsecutoreFinto()
    GhCli(esecutore=esecutore).crea_issue(BOZZA)
    comando, corpo = esecutore.chiamate[0]
    assert comando[:3] == ["gh", "issue", "create"]
    assert "--title" in comando and BOZZA.titolo in comando
    assert comando.count("--label") == 3
    assert "--body-file" in comando and "-" in comando
    assert corpo == BOZZA.corpo


def test_gh_che_fallisce_solleva_e_non_inventa_un_numero():
    esecutore = EsecutoreFinto(codice=1)
    with pytest.raises(GhNonDisponibile):
        GhCli(esecutore=esecutore).crea_issue(BOZZA)


def test_uscita_inattesa_solleva_invece_di_restituire_zero():
    esecutore = EsecutoreFinto(uscita="qualcosa di inatteso")
    with pytest.raises(GhNonDisponibile):
        GhCli(esecutore=esecutore).crea_issue(BOZZA)


def test_commenta_usa_issue_comment():
    esecutore = EsecutoreFinto(uscita="")
    GhCli(esecutore=esecutore).commenta(601, "altre 10 occorrenze")
    comando, corpo = esecutore.chiamate[0]
    assert comando[:3] == ["gh", "issue", "comment"]
    assert "601" in comando
    assert corpo == "altre 10 occorrenze"


def test_issue_chiusa_riconosciuta():
    esecutore = EsecutoreFinto(uscita='{"state":"CLOSED"}')
    assert GhCli(esecutore=esecutore).e_chiusa(601) is True


def test_issue_aperta_riconosciuta():
    esecutore = EsecutoreFinto(uscita='{"state":"OPEN"}')
    assert GhCli(esecutore=esecutore).e_chiusa(601) is False


def test_gh_irraggiungibile_durante_il_controllo_non_dichiara_chiusa():
    """Meglio non sapere che dichiarare chiusa una issue aperta e riaprirla doppia."""
    esecutore = EsecutoreFinto(codice=1)
    assert GhCli(esecutore=esecutore).e_chiusa(601) is None
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_gh.py -v`
Expected: FAIL con `ImportError: cannot import name 'GhCli'`

- [ ] **Step 3: Implementa**

```python
# src/error_watch/reporter.py — in coda
import json
import re
import subprocess

_RE_NUMERO_ISSUE = re.compile(r"/issues/(\d+)\s*$")


class GhNonDisponibile(RuntimeError):
    """`gh` assente, non autenticato, rate-limited o con uscita inattesa."""


def _esegui(comando: list[str], input: str | None = None) -> str:
    risultato = subprocess.run(
        comando,
        input=input,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return risultato.stdout


class GhCli:
    """Involucro sottile su `gh`. L'esecutore e' iniettabile per i test."""

    def __init__(self, esecutore=_esegui):
        self._esegui = esecutore

    def crea_issue(self, bozza: BozzaIssue) -> int:
        comando = ["gh", "issue", "create", "--title", bozza.titolo, "--body-file", "-"]
        for label in bozza.labels:
            comando += ["--label", label]
        try:
            uscita = self._esegui(comando, input=bozza.corpo)
        except Exception as errore:
            raise GhNonDisponibile(f"gh issue create fallito: {errore}") from errore
        match = _RE_NUMERO_ISSUE.search(uscita.strip())
        if match is None:
            raise GhNonDisponibile(f"uscita inattesa da gh: {uscita!r}")
        return int(match.group(1))

    def commenta(self, numero: int, testo: str) -> None:
        comando = ["gh", "issue", "comment", str(numero), "--body-file", "-"]
        try:
            self._esegui(comando, input=testo)
        except Exception as errore:
            raise GhNonDisponibile(f"gh issue comment fallito: {errore}") from errore

    def e_chiusa(self, numero: int) -> bool | None:
        """True/False, oppure None quando `gh` non risponde.

        None non e' un dettaglio: trattare un'incertezza come "chiusa" farebbe
        riaprire una issue gia' aperta come falsa regressione.
        """
        comando = ["gh", "issue", "view", str(numero), "--json", "state"]
        try:
            uscita = self._esegui(comando)
            return json.loads(uscita)["state"] == "CLOSED"
        except Exception:
            return None
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_gh.py -v`
Expected: PASS, 8 test

- [ ] **Step 5: Commit**

```bash
git add src/error_watch/reporter.py tests/error_watch/test_gh.py
git commit -m "feat(error-watch): involucro gh per apertura e commento delle issue"
```

---

### Task 12: CLI — orchestrazione, dry-run, heartbeat

**Files:**
- Create: `scripts/error_watch.py`
- Test: `tests/scripts/test_error_watch_cli.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/scripts/test_error_watch_cli.py
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import error_watch as cli  # scripts/ e' in pythonpath (pytest.ini)

ORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

TRACEBACK_CRITICO = """\
[2026-09-12 09:00:00,001: ERROR/ForkPoolWorker-1] Task fallita
Traceback (most recent call last):
  File "/app/src/workers/execution.py", line 100, in _submit
    submit(order)
KeyError: 'NVDA'
"""

TRACEBACK_NON_CRITICO = """\
[2026-09-12 09:00:00,001: ERROR/ForkPoolWorker-1] fetch fallita
Traceback (most recent call last):
  File "/app/src/connectors/marketaux.py", line 50, in fetch
    risposta.raise_for_status()
ValueError: 429
"""


class GhCheEsplode:
    """Doppio che FALLISCE se invocato.

    Un mock permissivo trasformerebbe il test "in dry-run non apre issue" in un
    assert che passa sempre, qualunque cosa faccia il codice.
    """

    def crea_issue(self, bozza):
        raise AssertionError("gh non deve essere invocato in questo scenario")

    def commenta(self, numero, testo):
        raise AssertionError("gh non deve essere invocato in questo scenario")

    def e_chiusa(self, numero):
        raise AssertionError("gh non deve essere invocato in questo scenario")


class GhRegistrante:
    def __init__(self):
        self.create = []
        self.commenti = []

    def crea_issue(self, bozza):
        self.create.append(bozza)
        return 600 + len(self.create)

    def commenta(self, numero, testo):
        self.commenti.append((numero, testo))

    def e_chiusa(self, numero):
        return False


@pytest.fixture
def ambiente(tmp_path: Path):
    """Un albero di log finto + una config che punta lì."""
    servizi = tmp_path / "containers"
    servizi.mkdir()
    stato = tmp_path / "stato"
    config = tmp_path / "error_watch.yaml"
    config.write_text(
        f"stato_dir: {stato}\n"
        f"sorgenti:\n"
        f"  servizi_dir: {servizi}\n"
        f"  cron_log_dir: {tmp_path / 'cron'}\n"
        "superficie_critica:\n"
        "  moduli:\n"
        "    - src/workers/execution.py\n"
        "  servizi_senza_frame:\n"
        "    - beat\n"
        "soglie:\n"
        "  occorrenze_non_critiche: 3\n"
        "  finestra_occorrenze_ore: 24\n"
        "  giorni_distinti_persistenza: 2\n"
        "  max_aperture_24h: 3\n"
        "  commento_dopo_silenzio_giorni: 7\n"
        "llm:\n"
        "  abilitato: false\n"
        "issue:\n"
        "  labels: [observability]\n"
    )
    return {"tmp": tmp_path, "servizi": servizi, "stato": stato, "config": config}


def test_dry_run_non_tocca_gh(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    esito = cli.giro(
        config=ambiente["config"], gh=GhCheEsplode(), ora=ORA, dry_run=True, notificatore=None
    )
    assert esito["aperture"] == 0
    assert esito["decisioni"]["apri"] == 1


def test_errore_critico_apre_una_issue(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    gh = GhRegistrante()
    esito = cli.giro(
        config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None
    )
    assert esito["aperture"] == 1
    assert len(gh.create) == 1
    assert "KeyError" in gh.create[0].titolo


def test_errore_non_critico_alla_prima_occorrenza_tace(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_NON_CRITICO)
    gh = GhRegistrante()
    esito = cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert esito["aperture"] == 0
    assert gh.create == []


def test_lo_stesso_errore_non_apre_due_issue(ambiente):
    log = ambiente["servizi"] / "worker-2026-09-12.log"
    log.write_text(TRACEBACK_CRITICO)
    gh = GhRegistrante()
    cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    log.write_text(TRACEBACK_CRITICO * 2)
    cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert len(gh.create) == 1


def test_loffset_impedisce_di_rileggere_le_stesse_righe(ambiente):
    log = ambiente["servizi"] / "worker-2026-09-12.log"
    log.write_text(TRACEBACK_CRITICO)
    gh = GhRegistrante()
    cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    secondo = cli.giro(
        config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None
    )
    assert secondo["eventi"] == 0


def test_baseline_censisce_senza_aprire(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO * 3)
    report = ambiente["tmp"] / "baseline.md"
    esito = cli.baseline(config=ambiente["config"], gh=GhCheEsplode(), destinazione=report)
    assert esito["aperture"] == 0
    testo = report.read_text()
    assert "KeyError" in testo
    assert "src/workers/execution.py:_submit" in testo


def test_baseline_silenzia_tutto_cio_che_ha_censito(ambiente):
    """Dopo la baseline il gate non deve svegliarsi sui fingerprint gia' noti."""
    log = ambiente["servizi"] / "worker-2026-09-12.log"
    log.write_text(TRACEBACK_CRITICO)
    cli.baseline(
        config=ambiente["config"], gh=GhCheEsplode(), destinazione=ambiente["tmp"] / "b.md"
    )
    log.write_text(TRACEBACK_CRITICO * 2)
    gh = GhRegistrante()
    esito = cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert esito["aperture"] == 0


def test_heartbeat_scritto_a_fine_giro(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    cli.giro(
        config=ambiente["config"], gh=GhRegistrante(), ora=ORA, dry_run=False, notificatore=None
    )
    heartbeat = ambiente["stato"] / "heartbeat"
    assert datetime.fromisoformat(heartbeat.read_text().strip()) == ORA


def test_heartbeat_vecchio_produce_un_avviso(ambiente):
    ambiente["stato"].mkdir(parents=True, exist_ok=True)
    vecchio = (ORA - timedelta(hours=5)).isoformat()
    (ambiente["stato"] / "heartbeat").write_text(vecchio)
    inviati = []
    esito = cli.giro(
        config=ambiente["config"],
        gh=GhRegistrante(),
        ora=ORA,
        dry_run=False,
        notificatore=lambda testo, livello: inviati.append((testo, livello)),
    )
    assert esito["heartbeat_stantio_minuti"] == pytest.approx(300, abs=1)
    assert any("fermo" in testo for testo, _ in inviati)


def test_un_log_illeggibile_non_ferma_gli_altri(ambiente, monkeypatch):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    (ambiente["servizi"] / "api-2026-09-12.log").write_text("irrilevante\n")
    originale = cli.leggi_nuove_righe

    def esplode_su_api(percorso, offset):
        if "api-" in percorso.name:
            raise OSError("permessi")
        return originale(percorso, offset)

    monkeypatch.setattr(cli, "leggi_nuove_righe", esplode_su_api)
    gh = GhRegistrante()
    esito = cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert esito["file_saltati"] == 1
    assert esito["aperture"] == 1


def test_gh_irraggiungibile_non_consuma_lo_stato(ambiente):
    """Se `gh` e' giu', il fingerprint resta da aprire e riprova al giro dopo."""

    class GhRotto:
        def crea_issue(self, bozza):
            from src.error_watch.reporter import GhNonDisponibile

            raise GhNonDisponibile("rate limit")

        def commenta(self, numero, testo):
            pass

        def e_chiusa(self, numero):
            return False

    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    esito = cli.giro(config=ambiente["config"], gh=GhRotto(), ora=ORA, dry_run=False, notificatore=None)
    assert esito["aperture"] == 0
    assert esito["aperture_fallite"] == 1
    gh = GhRegistrante()
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO * 2)
    secondo = cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert secondo["aperture"] == 1
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/scripts/test_error_watch_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'error_watch'`

- [ ] **Step 3: Implementa la CLI**

```python
#!/usr/bin/env python3
# scripts/error_watch.py
"""Sorveglianza degli errori di esecuzione: log -> fingerprint -> gate -> issue.

Uso:
    scripts/error_watch.py                      # giro normale
    scripts/error_watch.py --dry-run            # decide e stampa, non scrive su GitHub
    scripts/error_watch.py --baseline docs/evidence/error_watch_baseline_2026-09-12.md

Stampa un JSON di riepilogo su stdout. Exit 0 sempre che il giro sia arrivato
in fondo: un guasto parziale (un file illeggibile, `gh` giu') e' degradante,
non bloccante, e viene riportato nel JSON.

Spec: docs/superpowers/specs/2026-09-12-error-watch-design.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.error_watch import fingerprint as fp
from src.error_watch.collector import (
    byte_di,
    carica_offset,
    estrai_eventi,
    leggi_nuove_righe,
    salva_offset,
)
from src.error_watch.config import Config, carica_config
from src.error_watch.gate import decidi, e_critico
from src.error_watch.ledger import Ledger
from src.error_watch.modelli import Decisione, EventoGrezzo
from src.error_watch.reporter import GhCli, GhNonDisponibile, cliente_predefinito, redigi

_RE_NOME_LOG = re.compile(r"^(?P<servizio>.+)-(?P<data>\d{4}-\d{2}-\d{2})\.log$")


def _file_da_esaminare(cfg: Config) -> list[tuple[Path, str, date]]:
    trovati: list[tuple[Path, str, date]] = []
    if cfg.servizi_dir.is_dir():
        for percorso in sorted(cfg.servizi_dir.glob("*.log")):
            match = _RE_NOME_LOG.match(percorso.name)
            if match is None:
                continue
            trovati.append(
                (
                    percorso,
                    match.group("servizio"),
                    date.fromisoformat(match.group("data")),
                )
            )
    return trovati


def _sorgente_funzione(attribuzione: str) -> str:
    """Le righe della funzione incriminata, per il prompt del redattore."""
    modulo, _, funzione = attribuzione.partition(":")
    percorso = Path(modulo)
    if not percorso.is_file():
        return ""
    righe = percorso.read_text().splitlines()
    for indice, riga in enumerate(righe):
        if re.match(rf"\s*(async def|def) {re.escape(funzione)}\b", riga):
            return "\n".join(righe[indice : indice + 40])
    return ""


def _raccogli(cfg: Config) -> tuple[list[EventoGrezzo], int]:
    percorso_offset = cfg.stato_dir / "offsets.json"
    offsets = carica_offset(percorso_offset)
    eventi: list[EventoGrezzo] = []
    saltati = 0
    for percorso, servizio, giorno in _file_da_esaminare(cfg):
        chiave = str(percorso)
        try:
            righe, nuovo_offset = leggi_nuove_righe(percorso, offsets.get(chiave, 0))
        except OSError:
            saltati += 1
            continue
        if not righe:
            offsets[chiave] = nuovo_offset
            continue
        trovati, incompleto = estrai_eventi(righe, servizio=servizio, data_file=giorno)
        eventi.extend(trovati)
        if incompleto is not None:
            # Arretra: il traceback troncato va riletto intero al giro dopo.
            nuovo_offset -= byte_di(righe[incompleto:])
        offsets[chiave] = nuovo_offset
    salva_offset(percorso_offset, offsets)
    return eventi, saltati


def _heartbeat(cfg: Config, ora: datetime, notificatore) -> float | None:
    percorso = cfg.stato_dir / "heartbeat"
    eta = None
    try:
        precedente = datetime.fromisoformat(percorso.read_text().strip())
        minuti = (ora - precedente).total_seconds() / 60
        if minuti > cfg.heartbeat_eta_massima_minuti:
            eta = minuti
            if notificatore is not None:
                notificatore(
                    f"error_watch e' stato fermo {minuti / 60:.1f} ore "
                    f"(ultimo giro riuscito {precedente.isoformat()})",
                    "warning",
                )
    except (OSError, ValueError):
        pass
    return eta


def _scrivi_heartbeat(cfg: Config, ora: datetime) -> None:
    cfg.stato_dir.mkdir(parents=True, exist_ok=True)
    (cfg.stato_dir / "heartbeat").write_text(ora.isoformat())


def giro(
    *,
    config: Path,
    gh,
    ora: datetime | None = None,
    dry_run: bool = False,
    notificatore=None,
    cliente_llm=None,
) -> dict:
    """Un giro completo. Restituisce il riepilogo, non stampa nulla."""
    cfg = carica_config(config)
    ora = ora or datetime.now(timezone.utc)
    eta_heartbeat = _heartbeat(cfg, ora, notificatore)

    eventi, saltati = _raccogli(cfg)
    ledger = Ledger(cfg.stato_dir / "ledger.jsonl")
    decisioni: Counter[str] = Counter()
    aperture = 0
    aperture_fallite = 0

    for evento in eventi:
        chiave = fp.calcola(
            servizio=evento.servizio,
            tipo_eccezione=evento.tipo_eccezione,
            frames=evento.frames,
            messaggio=evento.messaggio,
        )
        attribuzione = fp.attribuzione(evento.frames)
        ledger.registra_occorrenza(
            fingerprint=chiave,
            servizio=evento.servizio,
            tipo_eccezione=evento.tipo_eccezione,
            attribuzione=attribuzione,
            messaggio=evento.messaggio,
            ts=evento.ts,
        )
        stato = ledger.stato(chiave)
        decisione = decidi(
            stato=stato,
            critico=e_critico(attribuzione=attribuzione, servizio=evento.servizio, cfg=cfg),
            ora=ora,
            cfg=cfg,
            aperture_24h=ledger.aperture_da(ora - timedelta(hours=24)),
        )
        decisioni[decisione.value] += 1

        if dry_run or decisione is Decisione.IGNORA:
            continue

        if decisione in (Decisione.APRI, Decisione.APRI_REGRESSIONE):
            bozza = asyncio.run(
                redigi(
                    stato=stato,
                    evento=evento,
                    cfg=cfg,
                    regressione=decisione is Decisione.APRI_REGRESSIONE,
                    cliente=cliente_llm,
                    sorgente=_sorgente_funzione(attribuzione),
                )
            )
            try:
                numero = gh.crea_issue(bozza)
            except GhNonDisponibile:
                # Lo stato NON viene consumato: si riprova al giro dopo.
                aperture_fallite += 1
                continue
            ledger.registra_issue(chiave, numero=numero, ts=ora)
            aperture += 1
            if notificatore is not None:
                notificatore(f"#{numero} {bozza.titolo}", "warning")
        elif decisione is Decisione.COMMENTA:
            try:
                gh.commenta(
                    stato.issue,
                    f"Ancora presente: {stato.conteggio} occorrenze totali, "
                    f"ultima {stato.ultimo_visto.isoformat()}.",
                )
            except GhNonDisponibile:
                continue
            ledger.registra_commento(chiave, ts=ora)
        elif decisione is Decisione.DIGEST and notificatore is not None:
            notificatore(
                f"Tappo raggiunto ({cfg.max_aperture_24h} aperture/24h): "
                f"{evento.tipo_eccezione} in {attribuzione} non ha aperto issue.",
                "warning",
            )

    _scrivi_heartbeat(cfg, ora)
    return {
        "eventi": len(eventi),
        "file_saltati": saltati,
        "decisioni": dict(decisioni),
        "aperture": aperture,
        "aperture_fallite": aperture_fallite,
        "heartbeat_stantio_minuti": eta_heartbeat,
        "righe_ledger_scartate": ledger.righe_scartate,
    }


def baseline(*, config: Path, gh, destinazione: Path) -> dict:
    """Censisce tutto lo storico senza aprire nulla, e silenzia ciò che ha visto."""
    cfg = carica_config(config)
    ora = datetime.now(timezone.utc)
    eventi, saltati = _raccogli(cfg)
    ledger = Ledger(cfg.stato_dir / "ledger.jsonl")
    for evento in eventi:
        chiave = fp.calcola(
            servizio=evento.servizio,
            tipo_eccezione=evento.tipo_eccezione,
            frames=evento.frames,
            messaggio=evento.messaggio,
        )
        ledger.registra_occorrenza(
            fingerprint=chiave,
            servizio=evento.servizio,
            tipo_eccezione=evento.tipo_eccezione,
            attribuzione=fp.attribuzione(evento.frames),
            messaggio=evento.messaggio,
            ts=evento.ts,
        )

    stati = sorted(ledger.tutti(), key=lambda stato: stato.conteggio, reverse=True)
    for stato in stati:
        ledger.silenzia(stato.fingerprint, motivo="baseline iniziale", ts=ora)

    righe = [
        f"# Baseline error_watch — {ora.date().isoformat()}",
        "",
        "Censimento in sola lettura dello storico dei log. **Nessuna issue aperta.**",
        "Ogni fingerprint qui elencato nasce silenziato: va tolto dal silenzio a mano",
        "(`logs/error_watch/silenziati.txt`) quello che merita una issue.",
        "",
        f"- Eventi esaminati: {len(eventi)}",
        f"- Fingerprint distinti: {len(stati)}",
        f"- File saltati: {saltati}",
        "",
        "| Conteggio | Giorni | Servizio | Eccezione | Attribuzione | Fingerprint |",
        "|---:|---:|---|---|---|---|",
    ]
    for stato in stati:
        righe.append(
            f"| {stato.conteggio} | {len(stato.giorni_distinti)} | {stato.servizio} "
            f"| {stato.tipo_eccezione} | `{stato.attribuzione}` | `{stato.fingerprint}` |"
        )
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_text("\n".join(righe) + "\n")
    return {"eventi": len(eventi), "fingerprint": len(stati), "aperture": 0}


def _notificatore_telegram():
    from src.notifications.telegram import TelegramNotifier

    notifier = TelegramNotifier()

    def invia(testo: str, livello: str) -> None:
        try:
            asyncio.run(notifier.send_alert(f"[error_watch] {testo}", level=livello))
        except Exception:  # Telegram giu' non deve fermare il giro
            pass

    return invia


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/error_watch.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--baseline", type=Path, help="scrive il censimento qui e non apre nulla")
    args = parser.parse_args(argv)

    cfg = carica_config(args.config)
    gh = GhCli()
    if args.baseline:
        esito = baseline(config=args.config, gh=gh, destinazione=args.baseline)
    else:
        esito = giro(
            config=args.config,
            gh=gh,
            dry_run=args.dry_run,
            notificatore=None if args.dry_run else _notificatore_telegram(),
            cliente_llm=cliente_predefinito() if cfg.llm_abilitato and not args.dry_run else None,
        )
    print(json.dumps(esito, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/scripts/test_error_watch_cli.py -v`
Expected: PASS, 11 test

- [ ] **Step 5: Esegui l'intera suite del modulo**

Run: `.venv/bin/python -m pytest tests/error_watch tests/scripts/test_error_watch_cli.py -v`
Expected: PASS, 113 test

- [ ] **Step 6: Commit**

```bash
git add scripts/error_watch.py tests/scripts/test_error_watch_cli.py
git commit -m "feat(error-watch): CLI con dry-run, baseline e heartbeat"
```

---

### Task 12b: Le due sorgenti che mancavano — log dei cron, `runs.jsonl`, `silenziati.txt`

La spec elenca tre ingressi che il Task 12 non consuma: i log dei job cron sull'host (`logs/*.log`, nominati `<job>_YYYY-MM-DD.log` con l'underscore, non col trattino come i servizi), il ledger degli exit code (`runs.jsonl`), e la denylist manuale (`silenziati.txt`, che il Task 15 crea ma che nessuno legge ancora). Senza questo task il sistema è cieco proprio sui cron, dove sono nati #396, #510 e #538.

**Files:**
- Modify: `src/error_watch/collector.py`, `scripts/error_watch.py`
- Test: `tests/error_watch/test_collector.py`, `tests/scripts/test_error_watch_cli.py`

- [ ] **Step 1: Scrivi i test che falliscono (collector)**

```python
# tests/error_watch/test_collector.py — in coda
from src.error_watch.collector import eventi_da_runs, servizio_e_data_da_nome


def test_nome_di_log_di_servizio_riconosciuto():
    assert servizio_e_data_da_nome("worker-inference-2026-09-12.log") == (
        "worker-inference",
        date(2026, 9, 12),
    )


def test_nome_di_log_di_cron_riconosciuto():
    assert servizio_e_data_da_nome("alpha_miss_analysis_2026-09-12.log") == (
        "alpha_miss_analysis",
        date(2026, 9, 12),
    )


def test_nome_senza_data_ignorato():
    assert servizio_e_data_da_nome("cron_crontab.log") is None


def test_exit_non_zero_diventa_un_evento(tmp_path: Path):
    righe = [
        '{"job":"daily_analysis","start":"2026-09-12T14:30:00Z","end":"2026-09-12T14:31:00Z",'
        '"exit_code":42,"righe_stderr":3,"traceback_visto":false}'
    ]
    eventi = eventi_da_runs(righe)
    assert len(eventi) == 1
    assert eventi[0].servizio == "daily_analysis"
    assert eventi[0].tipo_eccezione == "ExitNonZero"
    assert eventi[0].messaggio == "exit 42"
    assert eventi[0].frames == ()


def test_exit_zero_senza_traceback_non_produce_eventi():
    righe = [
        '{"job":"daily_analysis","start":"2026-09-12T14:30:00Z","end":"2026-09-12T14:31:00Z",'
        '"exit_code":0,"righe_stderr":0,"traceback_visto":false}'
    ]
    assert eventi_da_runs(righe) == []


def test_exit_zero_con_traceback_produce_un_evento():
    """La lezione di #396: un'eccezione puo' uscire con exit 0."""
    righe = [
        '{"job":"alpha_miner_dossier","start":"2026-09-12T08:00:00Z",'
        '"end":"2026-09-12T08:01:00Z","exit_code":0,"righe_stderr":18,"traceback_visto":true}'
    ]
    eventi = eventi_da_runs(righe)
    assert len(eventi) == 1
    assert eventi[0].tipo_eccezione == "TracebackConExitZero"


def test_riga_di_runs_corrotta_saltata():
    righe = ['{"job":"x", "exit_c', '{"job":"y","start":"2026-09-12T08:00:00Z",'
             '"end":"2026-09-12T08:01:00Z","exit_code":1,"righe_stderr":0,'
             '"traceback_visto":false}']
    eventi = eventi_da_runs(righe)
    assert len(eventi) == 1
    assert eventi[0].servizio == "y"
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: FAIL con `ImportError: cannot import name 'eventi_da_runs'`

- [ ] **Step 3: Implementa nel collector**

```python
# src/error_watch/collector.py — in coda

# I servizi usano il trattino (`worker-inference-2026-09-12.log`), i cron
# l'underscore (`alpha_miss_analysis_2026-09-12.log`). Un solo pattern con
# separatore alternativo, ancorato alla data, copre entrambi senza indovinare.
_RE_NOME_LOG = re.compile(r"^(?P<nome>.+)[-_](?P<data>\d{4}-\d{2}-\d{2})\.log$")


def servizio_e_data_da_nome(nome: str) -> tuple[str, date] | None:
    """Estrae (servizio-o-job, giorno) dal nome del file, o None se non datato."""
    match = _RE_NOME_LOG.match(nome)
    if match is None:
        return None
    try:
        return match.group("nome"), date.fromisoformat(match.group("data"))
    except ValueError:
        return None


def eventi_da_runs(righe: list[str]) -> list[EventoGrezzo]:
    """Trasforma i record di run_watched.sh in eventi.

    Due casi meritano attenzione, non uno:
    - `exit_code != 0`: il job e' fallito e lo dice.
    - `exit_code == 0` con un traceback su stderr: il job e' fallito e NON lo
      dice. E' il difetto di #396, e senza questo ramo resterebbe invisibile
      esattamente come allora.
    """
    eventi: list[EventoGrezzo] = []
    for riga in righe:
        if not riga.strip():
            continue
        try:
            record = json.loads(riga)
            job = record["job"]
            codice = int(record["exit_code"])
            fine = datetime.fromisoformat(record["end"].replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue

        if codice != 0:
            tipo, messaggio = "ExitNonZero", f"exit {codice}"
        elif record.get("traceback_visto"):
            tipo, messaggio = "TracebackConExitZero", "traceback su stderr con exit 0"
        else:
            continue

        eventi.append(
            EventoGrezzo(
                servizio=job,
                ts=fine,
                tipo_eccezione=tipo,
                messaggio=messaggio,
                frames=(),
                testo=riga.strip(),
                file_log="runs.jsonl",
                riga_log=0,
            )
        )
    return eventi
```

- [ ] **Step 4: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/error_watch/test_collector.py -v`
Expected: PASS, 23 test

- [ ] **Step 5: Scrivi i test che falliscono (CLI)**

```python
# tests/scripts/test_error_watch_cli.py — in coda


def test_legge_anche_i_log_dei_cron(ambiente):
    cron = ambiente["tmp"] / "cron"
    cron.mkdir()
    (cron / "daily_analysis_2026-09-12.log").write_text(TRACEBACK_NON_CRITICO * 3)
    gh = GhRegistrante()
    esito = cli.giro(config=ambiente["config"], gh=gh, ora=ORA, dry_run=False, notificatore=None)
    assert esito["eventi"] == 3
    assert esito["aperture"] == 1  # tre occorrenze in 24h


def test_ignora_i_log_senza_data_nel_nome(ambiente):
    cron = ambiente["tmp"] / "cron"
    cron.mkdir()
    (cron / "cron_crontab.log").write_text(TRACEBACK_CRITICO)
    esito = cli.giro(
        config=ambiente["config"], gh=GhCheEsplode(), ora=ORA, dry_run=True, notificatore=None
    )
    assert esito["eventi"] == 0


def test_exit_non_zero_di_un_cron_diventa_un_evento(ambiente):
    ambiente["stato"].mkdir(parents=True, exist_ok=True)
    (ambiente["stato"] / "runs.jsonl").write_text(
        '{"job":"deploy_reconcile","start":"2026-09-12T08:00:00Z",'
        '"end":"2026-09-12T08:01:00Z","exit_code":1,"righe_stderr":2,'
        '"traceback_visto":false}\n'
    )
    esito = cli.giro(
        config=ambiente["config"], gh=GhRegistrante(), ora=ORA, dry_run=False, notificatore=None
    )
    assert esito["eventi"] == 1


def test_silenziati_txt_rispettato(ambiente):
    """Il fingerprint in denylist non apre, anche se critico."""
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    primo = cli.giro(
        config=ambiente["config"], gh=GhCheEsplode(), ora=ORA, dry_run=True, notificatore=None
    )
    assert primo["decisioni"]["apri"] == 1
    fingerprint = primo["fingerprint_visti"][0]

    ambiente["stato"].mkdir(parents=True, exist_ok=True)
    (ambiente["stato"] / "silenziati.txt").write_text(
        f"# commento\n{fingerprint}  # rumore noto\n"
    )
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO * 2)
    secondo = cli.giro(
        config=ambiente["config"], gh=GhCheEsplode(), ora=ORA, dry_run=False, notificatore=None
    )
    assert secondo["aperture"] == 0


def test_silenziati_txt_assente_non_e_un_errore(ambiente):
    (ambiente["servizi"] / "worker-2026-09-12.log").write_text(TRACEBACK_CRITICO)
    esito = cli.giro(
        config=ambiente["config"], gh=GhRegistrante(), ora=ORA, dry_run=False, notificatore=None
    )
    assert esito["aperture"] == 1
```

- [ ] **Step 6: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/scripts/test_error_watch_cli.py -v`
Expected: FAIL — `esito["eventi"] == 0` sui log dei cron, e `KeyError: 'fingerprint_visti'`

- [ ] **Step 7: Estendi la CLI**

Sostituisci `_file_da_esaminare` e `_raccogli`, e aggiungi il caricamento della denylist:

```python
# scripts/error_watch.py — sostituisce _file_da_esaminare e _raccogli

def _file_da_esaminare(cfg: Config) -> list[tuple[Path, str, date]]:
    """Log dei servizi e log dei cron, uniti: un solo meccanismo per due mondi."""
    trovati: list[tuple[Path, str, date]] = []
    cartelle = [cfg.servizi_dir]
    if cfg.cron_log_dir != cfg.servizi_dir:
        cartelle.append(cfg.cron_log_dir)
    for cartella in cartelle:
        if not cartella.is_dir():
            continue
        for percorso in sorted(cartella.glob("*.log")):
            identificato = servizio_e_data_da_nome(percorso.name)
            if identificato is None:
                continue  # senza data nel nome non sappiamo a che giorno attribuirlo
            nome, giorno = identificato
            trovati.append((percorso, nome, giorno))
    return trovati


def carica_silenziati(cfg: Config) -> set[str]:
    """Denylist manuale dell'operatore. Un fingerprint per riga, `#` = commento."""
    percorso = cfg.stato_dir / "silenziati.txt"
    try:
        righe = percorso.read_text().splitlines()
    except OSError:
        return set()
    silenziati = set()
    for riga in righe:
        senza_commento = riga.split("#", 1)[0].strip()
        if senza_commento:
            silenziati.add(senza_commento)
    return silenziati


def _raccogli(cfg: Config) -> tuple[list[EventoGrezzo], int]:
    percorso_offset = cfg.stato_dir / "offsets.json"
    offsets = carica_offset(percorso_offset)
    eventi: list[EventoGrezzo] = []
    saltati = 0

    for percorso, servizio, giorno in _file_da_esaminare(cfg):
        chiave = str(percorso)
        try:
            righe, nuovo_offset = leggi_nuove_righe(percorso, offsets.get(chiave, 0))
        except OSError:
            saltati += 1
            continue
        if not righe:
            offsets[chiave] = nuovo_offset
            continue
        trovati, incompleto = estrai_eventi(righe, servizio=servizio, data_file=giorno)
        eventi.extend(trovati)
        if incompleto is not None:
            nuovo_offset -= byte_di(righe[incompleto:])
        offsets[chiave] = nuovo_offset

    # Ledger degli exit code: stessa lettura incrementale, sorgente diversa.
    runs = cfg.stato_dir / "runs.jsonl"
    chiave_runs = str(runs)
    try:
        righe_runs, offset_runs = leggi_nuove_righe(runs, offsets.get(chiave_runs, 0))
        eventi.extend(eventi_da_runs(righe_runs))
        offsets[chiave_runs] = offset_runs
    except OSError:
        saltati += 1

    salva_offset(percorso_offset, offsets)
    return eventi, saltati
```

Nell'import in testa al file aggiungi `eventi_da_runs` e `servizio_e_data_da_nome`:

```python
from src.error_watch.collector import (
    byte_di,
    carica_offset,
    estrai_eventi,
    eventi_da_runs,
    leggi_nuove_righe,
    salva_offset,
    servizio_e_data_da_nome,
)
```

E rimuovi `_RE_NOME_LOG` da `scripts/error_watch.py`: ora vive nel collector, dove è testato.

- [ ] **Step 8: Applica la denylist e riporta i fingerprint visti**

In `giro()`, dopo `ledger = Ledger(...)`:

```python
    silenziati = carica_silenziati(cfg)
    fingerprint_visti: list[str] = []
```

Dentro il ciclo, subito dopo `stato = ledger.stato(chiave)`:

```python
        fingerprint_visti.append(chiave)
        if chiave in silenziati and not stato.silenziato:
            # La denylist sopravvive a una ricostruzione del ledger: la si
            # riporta nel ledger cosi' il silenzio e' registrato, non implicito.
            ledger.silenzia(chiave, motivo="silenziati.txt", ts=ora)
            stato = ledger.stato(chiave)
```

E nel dizionario restituito aggiungi:

```python
        "fingerprint_visti": fingerprint_visti,
```

- [ ] **Step 9: Esegui e verifica che passino**

Run: `.venv/bin/python -m pytest tests/scripts/test_error_watch_cli.py -v`
Expected: PASS, 16 test

- [ ] **Step 10: Commit**

```bash
git add src/error_watch/collector.py scripts/error_watch.py tests/error_watch/test_collector.py tests/scripts/test_error_watch_cli.py
git commit -m "feat(error-watch): log dei cron, ledger degli exit code e denylist"
```

---

### Task 13: `run_watched.sh` — exit code dei job cron

**Files:**
- Create: `scripts/run_watched.sh`
- Test: `tests/scripts/test_run_watched.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# tests/scripts/test_run_watched.py
import json
import subprocess
from pathlib import Path

WRAPPER = Path("scripts/run_watched.sh").resolve()


def _esegui(tmp_path: Path, nome: str, *comando: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WRAPPER), nome, "--", *comando],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "ERROR_WATCH_RUNS": str(tmp_path / "runs.jsonl")},
    )


def _records(tmp_path: Path) -> list[dict]:
    return [
        json.loads(riga)
        for riga in (tmp_path / "runs.jsonl").read_text().splitlines()
        if riga.strip()
    ]


def test_exit_code_zero_propagato(tmp_path: Path):
    risultato = _esegui(tmp_path, "job-ok", "/bin/true")
    assert risultato.returncode == 0
    assert _records(tmp_path)[0]["exit_code"] == 0


def test_exit_code_non_zero_propagato_invariato(tmp_path: Path):
    """Un wrapper che mangia gli exit code reintrodurrebbe #396 un piano sopra."""
    risultato = _esegui(tmp_path, "job-ko", "/bin/sh", "-c", "exit 42")
    assert risultato.returncode == 42
    assert _records(tmp_path)[0]["exit_code"] == 42


def test_registra_nome_job_e_durata(tmp_path: Path):
    _esegui(tmp_path, "job-ok", "/bin/true")
    record = _records(tmp_path)[0]
    assert record["job"] == "job-ok"
    assert "start" in record and "end" in record


def test_stdout_del_comando_non_viene_inghiottito(tmp_path: Path):
    risultato = _esegui(tmp_path, "job-eco", "/bin/echo", "ciao")
    assert "ciao" in risultato.stdout


def test_conta_le_righe_di_stderr(tmp_path: Path):
    _esegui(tmp_path, "job-stderr", "/bin/sh", "-c", "echo a >&2; echo b >&2")
    assert _records(tmp_path)[0]["righe_stderr"] == 2


def test_traceback_su_stderr_segnalato(tmp_path: Path):
    _esegui(
        tmp_path,
        "job-tb",
        "/bin/sh",
        "-c",
        "echo 'Traceback (most recent call last):' >&2",
    )
    assert _records(tmp_path)[0]["traceback_visto"] is True


def test_comando_inesistente_non_rompe_il_ledger(tmp_path: Path):
    risultato = _esegui(tmp_path, "job-assente", "/bin/non-esiste-affatto")
    assert risultato.returncode != 0
    assert _records(tmp_path)[0]["job"] == "job-assente"
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `.venv/bin/python -m pytest tests/scripts/test_run_watched.py -v`
Expected: FAIL — `scripts/run_watched.sh` non esiste

- [ ] **Step 3: Implementa il wrapper**

```bash
#!/usr/bin/env bash
# scripts/run_watched.sh — esegue un job di cron registrandone l'esito.
#
#   scripts/run_watched.sh <nome-job> -- <comando> [argomenti...]
#
# Perche' esiste: i cron oggi loggano solo stdout, e l'exit code non compare da
# nessuna parte. Peggio, #396 ha mostrato che un'eccezione puo' uscire con
# `exit 0`. Questo wrapper registra {job, start, end, exit_code, righe_stderr,
# traceback_visto} in logs/error_watch/runs.jsonl e PROPAGA l'exit code
# invariato: se lo mangiasse, reintrodurrebbe lo stesso difetto un piano sopra.
#
# Non altera il comportamento del job: stdout ed stderr restano dove sono.

set -uo pipefail

NOME="${1:?manca il nome del job}"
shift
[[ "${1:-}" == "--" ]] && shift
[[ $# -gt 0 ]] || { echo "run_watched: manca il comando" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUNS="${ERROR_WATCH_RUNS:-$PROJECT_DIR/logs/error_watch/runs.jsonl}"
mkdir -p "$(dirname "$RUNS")"

STDERR_TMP="$(mktemp)"
trap 'rm -f "$STDERR_TMP"' EXIT

START="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
# stderr passa per una pipe verso `tee`, stdout scavalca la pipe via fd 3. Non
# usare `2> >(tee ...)`: la process substitution non viene attesa, e `wc -l`
# leggerebbe un file che il tee sta ancora scrivendo. Con la pipeline la shell
# aspetta il tee, e PIPESTATUS[0] resta l'exit code vero del job.
{ "$@" 2>&1 1>&3 | tee "$STDERR_TMP" >&2; } 3>&1
CODICE=${PIPESTATUS[0]}
END="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

RIGHE_STDERR=$(wc -l < "$STDERR_TMP" | tr -d ' ')
if grep -q "Traceback (most recent call last):" "$STDERR_TMP"; then
    TRACEBACK=true
else
    TRACEBACK=false
fi

printf '{"job":"%s","start":"%s","end":"%s","exit_code":%d,"righe_stderr":%s,"traceback_visto":%s}\n' \
    "$NOME" "$START" "$END" "$CODICE" "${RIGHE_STDERR:-0}" "$TRACEBACK" >> "$RUNS"

exit "$CODICE"
```

- [ ] **Step 4: Rendi eseguibile ed esegui i test**

```bash
chmod +x scripts/run_watched.sh
.venv/bin/python -m pytest tests/scripts/test_run_watched.py -v
```
Expected: PASS, 7 test

- [ ] **Step 5: Commit**

```bash
git add scripts/run_watched.sh tests/scripts/test_run_watched.py
git commit -m "feat(error-watch): wrapper cron che registra gli exit code"
```

---

### Task 14: `error_watch.sh` — wrapper di cron

**Files:**
- Create: `scripts/error_watch.sh`

- [ ] **Step 1: Scrivi il wrapper**

Segue lo stampo di `scripts/daily_s4_ic.sh`: PATH esplicito (cron parte con `/usr/bin:/bin` e senza questa riga il giro muore prima di cominciare — è già costato un guasto silenzioso, `bb74fa4`), log di sessione, caricamento selettivo delle due chiavi Telegram dal `.env`.

```bash
#!/usr/bin/env bash
# scripts/error_watch.sh — giro periodico della sorveglianza errori.
#
# Cron: ogni 15 minuti. Log: logs/error_watch_YYYY-MM-DD.log
# Spec: docs/superpowers/specs/2026-09-12-error-watch-design.md

set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
exec >>"$LOG_DIR/error_watch_${DATE}.log" 2>&1

# Lock: un giro lento non deve sovrapporsi al successivo e rileggere gli stessi
# offset due volte.
LOCK="$LOG_DIR/.error_watch.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') giro precedente ancora in corso, salto"
    exit 0
fi

cd "$PROJECT_DIR"

# Le credenziali Telegram non sono nell'ambiente del cron: senza queste righe la
# notifica verrebbe saltata in silenzio.
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

echo "=== error_watch $(date -u '+%Y-%m-%dT%H:%M:%SZ') $* ==="
# Gli argomenti passano oltre: serve per `error_watch.sh --dry-run`.
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/error_watch.py" "$@"
```

- [ ] **Step 2: Rendi eseguibile e verifica IN DRY-RUN**

> **Ordine non negoziabile:** la baseline (Task 15) non è ancora stata eseguita, quindi nessun fingerprint storico è silenziato. Un giro **non** in dry-run qui scandaglierebbe 60 giorni di log con il gate acceso e aprirebbe decine di issue vere — esattamente ciò che il bootstrap esiste per evitare. Il primo giro non-dry avviene al Task 15, dopo il censimento.

```bash
chmod +x scripts/error_watch.sh
scripts/error_watch.sh --dry-run && tail -5 logs/error_watch_$(date +%Y-%m-%d).log
```
Expected: il JSON di riepilogo nel log; `"aperture": 0` per costruzione (dry-run), e `decisioni` con molte voci `apri` — è la misura di quanto rumore c'è nello storico, e la ragione per cui la baseline viene prima

- [ ] **Step 3: Verifica che il lock funzioni**

```bash
(scripts/error_watch.sh --dry-run &) ; scripts/error_watch.sh --dry-run ; grep -c "salto" logs/error_watch_$(date +%Y-%m-%d).log
```
Expected: almeno `1` — il secondo giro non parte

- [ ] **Step 4: Commit**

```bash
git add scripts/error_watch.sh
git commit -m "feat(error-watch): wrapper cron con lock e credenziali Telegram"
```

---

### Task 15: Giro di baseline reale

**Files:**
- Create: `docs/evidence/error_watch_baseline_<oggi>.md`, `logs/error_watch/silenziati.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Escludi lo stato dal versionamento**

```bash
printf '\n# Stato locale della sorveglianza errori (il report di baseline invece si committa)\nlogs/error_watch/\n' >> .gitignore
```

- [ ] **Step 2: Esegui la baseline su tutto lo storico**

```bash
.venv/bin/python scripts/error_watch.py --baseline "docs/evidence/error_watch_baseline_$(date +%F).md"
```
Expected: JSON con `"aperture": 0` e `"fingerprint"` > 0

- [ ] **Step 3: Verifica che il gate sia davvero muto dopo la baseline**

```bash
.venv/bin/python scripts/error_watch.py --dry-run
```
Expected: `"aperture": 0` e `decisioni` senza voci `apri` — tutti i fingerprint storici nascono silenziati

- [ ] **Step 4: Leggi il censimento**

```bash
head -40 "docs/evidence/error_watch_baseline_$(date +%F).md"
```

**Questo è un punto di fermata per l'operatore.** La tabella va letta prima di andare avanti: ogni riga è un errore che il sistema sta già producendo in silenzio. Per ognuna, decidere se resta silenziata o se merita una issue aperta a mano. Il fingerprint noto al 2026-09-12 da tenere d'occhio è il `ValueError: connection limit exceeded` del `worker-news-stream` (100 occorrenze nel solo 2026-09-12, 69 il 2026-09-10): non è un difetto nostro per attribuzione, ma dice che lo stream news sta fallendo l'autenticazione.

- [ ] **Step 5: Crea il file dei silenziamenti permanenti**

```bash
cat > logs/error_watch/silenziati.txt <<'EOF'
# Fingerprint silenziati a mano, uno per riga, con il motivo dopo il #.
# I silenziamenti della baseline iniziale sono già nel ledger: questo file
# serve per quelli decisi dopo, e sopravvive a una ricostruzione del ledger.
EOF
```

- [ ] **Step 6: Primo giro live (ora è sicuro)**

```bash
scripts/error_watch.sh && tail -20 logs/error_watch_$(date +%F).log
```
Expected: `"aperture": 0` — tutto lo storico è silenziato, e da adesso il gate reagisce solo a ciò che è nuovo

- [ ] **Step 7: Commit del censimento**

```bash
git add .gitignore "docs/evidence/error_watch_baseline_$(date +%F).md"
git commit -m "docs(error-watch): censimento di baseline dei fingerprint storici"
```

---

### Task 16: Aggancio a cron

**Files:**
- Modify: crontab dell'utente (non versionato)
- Modify: `docs/operations.md`

- [ ] **Step 1: Aggiungi il giro periodico**

```bash
(crontab -l; cat <<'EOF'
# Sorveglianza errori di esecuzione: legge i log durevoli, deduplica per
# fingerprint, apre issue GitHub quando il gate lo richiede (2026-09-12).
*/15 * * * * /home/stefano/Documents/Projects/Alembic/scripts/error_watch.sh
EOF
) | crontab -
crontab -l | grep error_watch
```
Expected: la riga compare

- [ ] **Step 2: Avvolgi i job cron esistenti in `run_watched.sh`**

Una voce per volta, verificando dopo ognuna. Esempio per il primo:

```bash
crontab -l | sed 's#^30 14 \* \* 1-5 /home/stefano/Documents/Projects/Alembic/scripts/daily_analysis.sh#30 14 * * 1-5 /home/stefano/Documents/Projects/Alembic/scripts/run_watched.sh daily_analysis -- /home/stefano/Documents/Projects/Alembic/scripts/daily_analysis.sh#' | crontab -
crontab -l | grep daily_analysis
```

Ripeti per: `auto_arm_shadow_monday`, `deadline_reminder`, `daily_alpha_miss_analysis`, `roadmap_agent_loop` (entrambe le voci, nomi `roadmap_loop` e `roadmap_loop_codex`), `deploy_reconcile`, `roadmap_health_check`, `s4_cluster_monitor`, `check_s4_trial_milestones`, `daily_s4_ic`.

- [ ] **Step 3: Verifica che il ledger dei run si popoli**

Dopo il primo job schedulato:
```bash
tail -3 logs/error_watch/runs.jsonl
```
Expected: un record per ogni job eseguito, con `exit_code`

- [ ] **Step 4: Documenta in `docs/operations.md`**

Aggiungi una sezione che dica: dove vive lo stato (`logs/error_watch/`), come silenziare un fingerprint (aggiungerlo a `silenziati.txt`), come rileggere il censimento (`--baseline` su una destinazione nuova), e come spegnere tutto (commentare la riga di crontab — il sistema non ha altri effetti).

- [ ] **Step 5: Commit**

```bash
git add docs/operations.md
git commit -m "docs(error-watch): operazioni, silenziamenti e spegnimento"
```

---

### Task 17: Verifica finale

- [ ] **Step 1: Suite completa del modulo**

Run: `.venv/bin/python -m pytest tests/error_watch tests/scripts/test_error_watch_cli.py tests/scripts/test_run_watched.py -v`
Expected: PASS, 120 test

- [ ] **Step 2: Suite completa del repo (nessuna regressione)**

Run: `.venv/bin/python -m pytest -q`
Expected: nessun fallimento nuovo rispetto al conteggio di `main`

- [ ] **Step 3: Prova end-to-end con un errore finto**

```bash
printf 'Traceback (most recent call last):\n  File "/app/src/workers/execution.py", line 999, in _prova_error_watch\n    raise KeyError("PROVA")\nKeyError: %s\n' "'PROVA'" \
  >> logs/containers/worker-$(date +%F).log
.venv/bin/python scripts/error_watch.py --dry-run
```
Expected: `decisioni` contiene `"apri": 1` — la superficie critica scatta alla prima occorrenza

- [ ] **Step 4: Togli la riga finta**

```bash
sed -i '/_prova_error_watch/,+1d' logs/containers/worker-$(date +%F).log
```

Nota: l'offset è già avanzato oltre quelle righe, quindi non verranno riesaminate. Il fingerprint di prova resta nel ledger con una sola occorrenza e nessuna issue: innocuo.

- [ ] **Step 5: Apri la issue di tracciamento**

```bash
gh issue create \
  --title "error_watch: sorveglianza degli errori di esecuzione" \
  --body "Implementa docs/superpowers/specs/2026-09-12-error-watch-design.md. Part of #21." \
  --label observability --label freeze-ok
```
