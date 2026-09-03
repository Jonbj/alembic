# Review notturna delle PR sul modello locale — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una volta a notte, far esaminare al worker locale Qwen3.8-27B una PR aperta contro la issue che dichiara di chiudere, e pubblicare i soli rilievi come commento sulla PR.

**Architecture:** Quattro moduli puri in `src/review_locale/` portano tutta la logica verificabile (validazione del referto, rilevatori di loop, politica di selezione, estrazione e filtro del diff). Un orchestratore in `scripts/review_notturna_locale.py` concentra l'impuro: `systemctl`, `gh`, la chiamata HTTP in streaming al server locale, la scrittura del ledger. Un timer systemd utente lo lancia all'01:07.

**Tech Stack:** Python 3.14, pytest (`.venv/bin/python -m pytest`), `httpx` (già dipendenza), `gh` CLI, systemd user units. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-09-03-review-notturna-locale-design.md`

---

## Contesto che serve a chi implementa

Il worker locale è un `llama-server` già configurato come unit **utente** (non di sistema): `systemctl --user start llama-server.service`, poi `curl -s http://127.0.0.1:8080/health` deve rispondere `{"status":"ok"}` (~15 s). L'endpoint è OpenAI-compatibile su `http://127.0.0.1:8080/v1/chat/completions`, api-key `not-needed`, alias modello `qwen3.8-27b-local`. Ha **un solo slot**: mai due richieste in parallelo.

Genera a **~1,3 token/s**. Un referto completo costa 3-4 ore. Questo non è un problema da risolvere, è il vincolo intorno a cui il disegno è costruito.

Il principio che governa tutto: **il modello è una lente che esamina, mai un cancello che approva.** La misura che lo impone è in §2 della spec. In pratica: il campo `verificato_e_scartato` del suo JSON non deve **mai** raggiungere GitHub, e un referto senza rilievi non produce commento.

Convenzioni del repo da rispettare: moduli puri con docstring in italiano che inizia dichiarando la purezza (vedi `src/analysis/dossier/timeline.py`); test in italiano in `tests/<area>/`; `pytest.ini` ha `pythonpath = scripts`, quindi gli script sono importabili come moduli nei test.

---

## Struttura dei file

| File | Responsabilità |
|---|---|
| `src/review_locale/__init__.py` | package vuoto |
| `src/review_locale/referto.py` | valida il JSON del modello, scarta le assoluzioni, decide se è pubblicabile |
| `src/review_locale/rilevatori.py` | misura la ripetizione del ragionamento; decide loop e corsa condannata |
| `src/review_locale/selezione.py` | dato ledger + PR aperte, scegli quale esaminare |
| `src/review_locale/estrazione.py` | filtra il diff ai file di codice, taglia a 35 KB, costruisce i prompt |
| `scripts/review_notturna_locale.py` | orchestratore: systemctl, gh, httpx streaming, ledger |
| `tests/review_locale/__init__.py` | package dei test |
| `tests/review_locale/test_referto.py` | il test che protegge il principio |
| `tests/review_locale/test_rilevatori.py` | calibrazione su campioni reali + loop sintetico |
| `tests/review_locale/test_selezione.py` | politica del ledger |
| `tests/review_locale/test_estrazione.py` | filtro, tetto, spezzatura |
| `tests/scripts/test_review_notturna_locale.py` | integrazione con `gh` e server finti |
| `~/.config/systemd/user/review-notturna-locale.service` | unit (fuori dal repo) |
| `~/.config/systemd/user/review-notturna-locale.timer` | timer 01:07 (fuori dal repo) |

L'ordine dei task non è arbitrario: **Task 1 per primo** perché è il test che protegge il principio dell'intera spec. Se quello non esiste, ogni altro pezzo può violarlo silenziosamente.

---

### Task 1: `referto.py` — la guardia del principio

**Files:**
- Create: `src/review_locale/__init__.py`
- Create: `src/review_locale/referto.py`
- Create: `tests/review_locale/__init__.py`
- Test: `tests/review_locale/test_referto.py`

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/review_locale/__init__.py` vuoto e `src/review_locale/__init__.py` vuoto, poi `tests/review_locale/test_referto.py`:

```python
"""Validazione del referto del modello locale (spec 2026-09-03).

Il test che conta e' `test_verificato_e_scartato_non_esce_mai`: protegge il
principio dell'intera spec — le assoluzioni del modello non raggiungono GitHub.
"""

import json

from src.review_locale.referto import prepara


def _referto(rilievi, con_assoluzioni=True) -> str:
    corpo = {
        "rilievi": rilievi,
        "criteri_issue": [{"criterio": "c", "esito": "SODDISFATTO", "perche": "p"}],
        "informazioni_mancanti": [],
        "confidenza": 0.8,
    }
    if con_assoluzioni:
        corpo["verificato_e_scartato"] = [
            "La SQL esclude correttamente SKIP_THRESHOLD",
            "La partizione actionability e' completa",
        ]
    return json.dumps(corpo)


_RILIEVO = {
    "gravita": "ALTA",
    "categoria": "classificazione_sbagliata",
    "posizione": "src/x.py:10",
    "difetto": "d",
    "scenario_di_fallimento": "s",
    "mascherato_da": None,
}


def test_verificato_e_scartato_non_esce_mai():
    """Le assoluzioni del modello non compaiono in nulla di pubblicabile.

    Su PR #472 il modello ha prodotto 11 voci in `verificato_e_scartato`, di cui
    almeno 2 dimostrabilmente false, e false esattamente sui due punti dove i
    difetti erano reali. Pubblicarle equivarrebbe a pubblicare un via libera
    sbagliato.
    """
    esito = prepara(_referto([_RILIEVO]))

    assert esito.stato == "PUBBLICABILE"
    serializzato = json.dumps(esito.rilievi)
    assert "verificato_e_scartato" not in serializzato
    assert "correttamente" not in serializzato
    assert "completa" not in serializzato


def test_rilievi_vuoti_non_sono_pubblicabili():
    esito = prepara(_referto([]))

    assert esito.stato == "SENZA_RILIEVI"
    assert esito.rilievi == ()


def test_json_invalido_non_e_pubblicabile():
    esito = prepara("{questo non e' JSON")

    assert esito.stato == "NON_VALIDO"
    assert esito.causa is not None
    assert esito.rilievi == ()


def test_rilievi_non_lista_e_trattato_come_non_valido():
    esito = prepara(json.dumps({"rilievi": "due"}))

    assert esito.stato == "NON_VALIDO"


def test_rilievo_senza_scenario_e_scartato():
    """Un rilievo senza scenario concreto non e' azionabile: non si pubblica.

    Lo schema del prompt chiede uno scenario di fallimento per ogni rilievo. Un
    rilievo che non lo porta e' una preoccupazione generica.
    """
    incompleto = dict(_RILIEVO)
    del incompleto["scenario_di_fallimento"]

    esito = prepara(_referto([incompleto]))

    assert esito.stato == "SENZA_RILIEVI"


def test_rilievi_validi_e_invalidi_insieme_tiene_solo_i_validi():
    incompleto = dict(_RILIEVO)
    del incompleto["scenario_di_fallimento"]

    esito = prepara(_referto([_RILIEVO, incompleto]))

    assert esito.stato == "PUBBLICABILE"
    assert len(esito.rilievi) == 1


def test_referto_senza_assoluzioni_resta_valido():
    esito = prepara(_referto([_RILIEVO], con_assoluzioni=False))

    assert esito.stato == "PUBBLICABILE"
    assert len(esito.rilievi) == 1
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/review_locale/test_referto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.review_locale.referto'`

- [ ] **Step 3: Scrivi l'implementazione minima**

`src/review_locale/referto.py`:

```python
"""Validazione del referto prodotto dal modello locale (spec 2026-09-03).

Modulo puro: riceve il testo che il modello ha emesso e non tocca rete, disco o
processi.

La regola che questo modulo esiste per imporre: **su GitHub va solo un referto
completo con almeno un rilievo azionabile.** Il campo `verificato_e_scartato`
— le "verifiche" con cui il modello dichiara corretto cio' che ha guardato —
non attraversa questo confine in nessuna circostanza. Su PR #472 ne ha prodotte
undici, di cui almeno due false, e false esattamente sui due punti dove i
difetti erano reali: e' una lente che esamina, non un cancello che approva.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Chiavi che ogni rilievo deve portare per essere azionabile. `mascherato_da`
# resta fuori: e' informativa e legittimamente assente.
CHIAVI_RILIEVO = ("gravita", "categoria", "posizione", "difetto", "scenario_di_fallimento")

PUBBLICABILE = "PUBBLICABILE"
SENZA_RILIEVI = "SENZA_RILIEVI"
NON_VALIDO = "NON_VALIDO"


@dataclass(frozen=True)
class Esito:
    """Cosa e' uscito dal referto, e cosa se ne puo' fare.

    `rilievi` contiene SOLO rilievi completi, e per costruzione nessuna
    assoluzione: e' l'unico campo che l'orchestratore ha il diritto di
    pubblicare.
    """

    stato: str
    rilievi: tuple[dict[str, Any], ...] = ()
    causa: str | None = None


def _rilievo_completo(rilievo: Any) -> bool:
    if not isinstance(rilievo, dict):
        return False
    return all(rilievo.get(chiave) for chiave in CHIAVI_RILIEVO)


def prepara(testo: str) -> Esito:
    """Trasforma il testo emesso dal modello in un esito pubblicabile o no."""
    try:
        corpo = json.loads(testo)
    except (json.JSONDecodeError, TypeError) as exc:
        return Esito(NON_VALIDO, causa=f"JSON non parsabile: {exc}")

    if not isinstance(corpo, dict):
        return Esito(NON_VALIDO, causa="il referto non e' un oggetto JSON")

    grezzi = corpo.get("rilievi")
    if not isinstance(grezzi, list):
        return Esito(NON_VALIDO, causa="il campo `rilievi` manca o non e' una lista")

    # Si ricostruiscono i rilievi chiave per chiave invece di filtrare il corpo:
    # cosi' nessun campo del modello puo' passare per inerzia, incluse le
    # assoluzioni e qualunque chiave nuova che il modello inventasse.
    validi = tuple(
        {chiave: rilievo[chiave] for chiave in CHIAVI_RILIEVO}
        | {"mascherato_da": rilievo.get("mascherato_da")}
        for rilievo in grezzi
        if _rilievo_completo(rilievo)
    )

    if not validi:
        return Esito(SENZA_RILIEVI)
    return Esito(PUBBLICABILE, rilievi=validi)
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/review_locale/test_referto.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/review_locale/__init__.py src/review_locale/referto.py \
        tests/review_locale/__init__.py tests/review_locale/test_referto.py
git commit -m "feat(review-locale): validazione del referto, le assoluzioni non escono

Il modulo impone la regola centrale della spec: pubblicabile solo un referto
con almeno un rilievo completo, e \`verificato_e_scartato\` scartato sempre.
I rilievi sono ricostruiti chiave per chiave, non filtrati, cosi' nessun campo
del modello passa per inerzia."
```

---

### Task 2: `rilevatori.py` — loop e corsa condannata

**Files:**
- Create: `src/review_locale/rilevatori.py`
- Test: `tests/review_locale/test_rilevatori.py`

- [ ] **Step 1: Scrivi il test che fallisce**

`tests/review_locale/test_rilevatori.py`:

```python
"""Rilevatori di loop e di corsa condannata (spec 2026-09-03 §5).

Le soglie sono calibrate su due campioni reali del 2026-09-02: un ragionamento
sano di 23.653 caratteri portava 2 righe ripetute e 1 solo 12-gramma ripetuto.
"""

from src.review_locale.rilevatori import (
    e_corsa_condannata,
    e_loop,
    misura_ripetizione,
)


def test_ragionamento_sano_non_e_loop():
    """Un testo che avanza non produce ripetizione, anche se lungo."""
    testo = "\n".join(
        f"Considero ora il ramo numero {i} della classificazione e valuto "
        f"se la condizione a monte possa produrre questo esito nel caso {i}."
        for i in range(200)
    )

    misure = misura_ripetizione(testo)

    assert misure["dodici_grammi_ripetuti"] == 0
    assert not e_loop(misure)


def test_citazione_ripetuta_non_conta_come_loop():
    """Il campione reale sano ripeteva 2 righe: due citazioni. Non e' un loop."""
    citazione = "NO_RELEVANT_NEWS, LATE_NEWS, ENTITY_ERROR, NO_SIGNAL, WRONG_SIGN, BELOW_GATE"
    testo = "\n".join(
        [citazione]
        + [f"Passo {i}: verifico la condizione sul ramo {i} del funnel v2." for i in range(50)]
        + [citazione]
    )

    misure = misura_ripetizione(testo)

    assert misure["righe_ripetute"] == 1
    assert not e_loop(misure)


def test_loop_vero_e_rilevato():
    """Lo stesso paragrafo ripetuto molte volte supera la soglia."""
    paragrafo = (
        "Devo verificare se il ramo OUT_OF_SCOPE sia raggiungibile oppure no, "
        "quindi torno a controllare la condizione in universo del mover."
    )
    testo = "\n".join([paragrafo] * 30)

    misure = misura_ripetizione(testo)

    assert misure["dodici_grammi_ripetuti"] > 10
    assert e_loop(misure)


def test_soglia_loop_e_configurabile():
    testo = "\n".join(["la stessa frase ripetuta molte volte senza mai avanzare di un passo"] * 15)
    misure = misura_ripetizione(testo)

    assert e_loop(misure, soglia_dodici_grammi=5)
    assert not e_loop(misure, soglia_dodici_grammi=10_000)


def test_corsa_condannata_solo_con_content_vuoto():
    """A 28.000 token di ragionamento senza JSON, il tetto non basta piu'."""
    assert e_corsa_condannata(token_ragionamento=28_000, content_vuoto=True)
    assert not e_corsa_condannata(token_ragionamento=28_000, content_vuoto=False)


def test_corsa_sana_non_e_condannata():
    """Il run riuscito su PR #472: 16.453 token totali, ~14.400 di ragionamento."""
    assert not e_corsa_condannata(token_ragionamento=14_400, content_vuoto=True)


def test_tetto_corsa_condannata_e_configurabile():
    assert e_corsa_condannata(token_ragionamento=1_000, content_vuoto=True, tetto=500)
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/review_locale/test_rilevatori.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.review_locale.rilevatori'`

- [ ] **Step 3: Scrivi l'implementazione minima**

`src/review_locale/rilevatori.py`:

```python
"""Rilevatori sullo stream del modello locale (spec 2026-09-03 §5).

Modulo puro: riceve il ragionamento accumulato e dei contatori, non tocca rete
ne' processi.

Nessuna regola di orologio: un orologio non distingue un lavoro lento da un
lavoro rotto. Il limite lo pongono due misure su cio' che il modello sta
effettivamente producendo — la ripetizione, che identifica il loop vero, e il
budget residuo, che identifica la corsa aritmeticamente incapace di chiudere.

Calibrazione (2026-09-02, due campioni): un ragionamento sano di 23.653
caratteri portava 2 righe ripetute e 1 solo 12-gramma ripetuto; il run che ha
concluso ne aveva 54.958. La soglia a 10 e' quindi deliberatamente larga: con
due soli campioni non vale la pena uccidere un ragionamento sano che ripete una
citazione. `misura_ripetizione` va loggata a ogni giro, cosi' la soglia si
scegliera' sui dati.
"""

from __future__ import annotations

import collections
import re


# Sotto le 60 battute una riga e' un frammento, non un passo di ragionamento.
LUNGHEZZA_MINIMA_RIGA = 60

# 12 parole: abbastanza lungo perche' una coincidenza sia improbabile,
# abbastanza corto per cogliere un paragrafo riformulato.
AMPIEZZA_GRAMMA = 12

SOGLIA_DODICI_GRAMMI = 10

# `max_tokens` e' 32.768 e il JSON del referto su PR #472 e' costato ~2.000
# token: oltre questo punto, con `content` ancora vuoto, il residuo non basta.
TETTO_RAGIONAMENTO = 28_000


def misura_ripetizione(ragionamento: str) -> dict[str, int]:
    """Quanto il ragionamento si ripete: righe identiche e 12-grammi."""
    righe = [
        riga.strip()
        for riga in ragionamento.split("\n")
        if len(riga.strip()) > LUNGHEZZA_MINIMA_RIGA
    ]
    conteggio_righe = collections.Counter(righe)
    righe_ripetute = sum(n - 1 for n in conteggio_righe.values() if n > 1)

    parole = re.findall(r"\w+", ragionamento.lower())
    grammi = collections.Counter(
        tuple(parole[i:i + AMPIEZZA_GRAMMA])
        for i in range(max(0, len(parole) - AMPIEZZA_GRAMMA))
    )
    dodici_grammi_ripetuti = sum(1 for n in grammi.values() if n > 2)

    return {
        "righe_sostanziali": len(righe),
        "righe_ripetute": righe_ripetute,
        "dodici_grammi_ripetuti": dodici_grammi_ripetuti,
    }


def e_loop(misure: dict[str, int], soglia_dodici_grammi: int = SOGLIA_DODICI_GRAMMI) -> bool:
    """True se il ragionamento gira a vuoto invece di avanzare."""
    return misure["dodici_grammi_ripetuti"] > soglia_dodici_grammi


def e_corsa_condannata(
    token_ragionamento: int,
    content_vuoto: bool,
    tetto: int = TETTO_RAGIONAMENTO,
) -> bool:
    """True se il budget residuo non basta piu' per emettere il referto."""
    return content_vuoto and token_ragionamento >= tetto
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/review_locale/test_rilevatori.py -v`
Expected: PASS, 7 passed

Se `test_citazione_ripetuta_non_conta_come_loop` fallisse su `righe_ripetute == 1`: la citazione compare due volte, quindi `n - 1 == 1`. È il conteggio delle ripetizioni *in eccesso*, non delle righe coinvolte — coerente con la misura fatta a mano il 02/09.

- [ ] **Step 5: Commit**

```bash
git add src/review_locale/rilevatori.py tests/review_locale/test_rilevatori.py
git commit -m "feat(review-locale): rilevatori di loop e corsa condannata

Nessuna regola di orologio: la ripetizione di 12-grammi identifica il loop
vero, il budget residuo la corsa che non puo' piu' chiudere. Soglie calibrate
sui due campioni reali del 02/09 e deliberatamente larghe."
```

---

### Task 3: `selezione.py` — quale PR stanotte

**Files:**
- Create: `src/review_locale/selezione.py`
- Test: `tests/review_locale/test_selezione.py`

- [ ] **Step 1: Scrivi il test che fallisce**

`tests/review_locale/test_selezione.py`:

```python
"""Politica di selezione della PR da esaminare (spec 2026-09-03 §4)."""

from src.review_locale.selezione import PrCandidata, scegli


def _pr(numero: int, sha: str, creata_il: str) -> PrCandidata:
    return PrCandidata(numero=numero, sha=sha, creata_il=creata_il)


def _voce(numero: int, sha: str, stato: str) -> dict:
    return {"pr": numero, "sha": sha, "stato": stato}


def test_ledger_vuoto_prende_la_piu_vecchia():
    scelta = scegli(
        [
            _pr(480, "aaa", "2026-09-02T10:00:00Z"),
            _pr(472, "bbb", "2026-09-02T08:00:00Z"),
        ],
        ledger=[],
    )

    assert scelta is not None
    assert scelta.numero == 472


def test_pr_gia_esaminata_non_torna():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is None


def test_esaminata_senza_rilievi_conta_come_esaminata():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_SENZA_RILIEVI")],
    )

    assert scelta is None


def test_nuovo_commit_riapre_la_pr():
    """L'identita' dell'esame e' (numero, sha), non il numero."""
    scelta = scegli(
        [_pr(472, "ccc", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is not None
    assert scelta.sha == "ccc"


def test_un_tentativo_fallito_non_esaurisce_lo_sha():
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is not None


def test_due_tentativi_falliti_esauriscono_lo_sha():
    """Stop rule del NODE_CONTRACT: due tentativi per sha, poi basta."""
    scelta = scegli(
        [_pr(472, "bbb", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA"), _voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is None


def test_sha_esaurito_non_blocca_un_commit_nuovo():
    scelta = scegli(
        [_pr(472, "ccc", "2026-09-02T08:00:00Z")],
        ledger=[_voce(472, "bbb", "NON_ESAMINATA"), _voce(472, "bbb", "NON_ESAMINATA")],
    )

    assert scelta is not None
    assert scelta.sha == "ccc"


def test_nessuna_pr_aperta_non_e_un_errore():
    assert scegli([], ledger=[]) is None


def test_salta_la_esaurita_e_prende_la_successiva():
    scelta = scegli(
        [
            _pr(472, "bbb", "2026-09-02T08:00:00Z"),
            _pr(480, "aaa", "2026-09-02T10:00:00Z"),
        ],
        ledger=[_voce(472, "bbb", "ESAMINATA_CON_RILIEVI")],
    )

    assert scelta is not None
    assert scelta.numero == 480
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/review_locale/test_selezione.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.review_locale.selezione'`

- [ ] **Step 3: Scrivi l'implementazione minima**

`src/review_locale/selezione.py`:

```python
"""Quale PR esaminare stanotte (spec 2026-09-03 §4).

Modulo puro: riceve l'elenco delle PR aperte e le voci del ledger gia' lette,
non chiama `gh` ne' legge file.

Una PR per notte, la piu' vecchia non ancora esaminata: a ~4 ore per referto il
ritmo reale e' uno, e riempire la notte con le PR piu' piccole rimanderebbe per
sempre quelle grandi, che sono dove i difetti si nascondono.

L'identita' dell'esame e' `(numero, sha del head)`: nuovi commit riaprono una PR
gia' esaminata, perche' il referto vecchio parlava di un altro codice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


MAX_TENTATIVI = 2

STATI_ESAMINATA = ("ESAMINATA_CON_RILIEVI", "ESAMINATA_SENZA_RILIEVI")
STATO_FALLITO = "NON_ESAMINATA"


@dataclass(frozen=True)
class PrCandidata:
    numero: int
    sha: str
    creata_il: str


def scegli(
    candidate: Iterable[PrCandidata],
    ledger: Iterable[dict[str, Any]],
    max_tentativi: int = MAX_TENTATIVI,
) -> PrCandidata | None:
    """La PR da esaminare, o None se non ce n'e' nessuna eleggibile."""
    voci = list(ledger)
    esaminate = {
        (voce["pr"], voce["sha"])
        for voce in voci
        if voce.get("stato") in STATI_ESAMINATA
    }
    tentativi: dict[tuple[int, str], int] = {}
    for voce in voci:
        if voce.get("stato") == STATO_FALLITO:
            chiave = (voce["pr"], voce["sha"])
            tentativi[chiave] = tentativi.get(chiave, 0) + 1

    eleggibili = [
        pr
        for pr in candidate
        if (pr.numero, pr.sha) not in esaminate
        and tentativi.get((pr.numero, pr.sha), 0) < max_tentativi
    ]
    if not eleggibili:
        return None
    return min(eleggibili, key=lambda pr: pr.creata_il)
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/review_locale/test_selezione.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/review_locale/selezione.py tests/review_locale/test_selezione.py
git commit -m "feat(review-locale): politica di selezione della PR

Una per notte, la piu' vecchia non esaminata. L'identita' dell'esame e'
(numero, sha): nuovi commit riaprono la PR. Due tentativi per sha, come la
stop rule del NODE_CONTRACT."
```

---

### Task 4: `estrazione.py` — filtro del diff e costruzione del prompt

**Files:**
- Create: `src/review_locale/estrazione.py`
- Test: `tests/review_locale/test_estrazione.py`

Il caso che giustifica questo modulo è PR #477: +69.343 righe, di cui 58.339 sono un dossier JSON generato. Il codice vero è ~2.000 righe. **Non committare il diff reale come fixture** — sono ~2 MB. La fixture riproduce la forma: un file di dati enorme più due file di codice piccoli.

- [ ] **Step 1: Scrivi il test che fallisce**

`tests/review_locale/test_estrazione.py`:

```python
"""Filtro del diff e costruzione dei prompt (spec 2026-09-03 §4)."""

from src.review_locale.estrazione import costruisci_prompt, file_toccati, filtra_diff


def _hunk(percorso: str, righe: int) -> str:
    corpo = "\n".join(f"+riga di contenuto numero {i}" for i in range(righe))
    return (
        f"diff --git a/{percorso} b/{percorso}\n"
        f"index 0000000..1111111 100644\n"
        f"--- a/{percorso}\n"
        f"+++ b/{percorso}\n"
        f"@@ -0,0 +1,{righe} @@\n"
        f"{corpo}\n"
    )


ISSUE = "## What to build\n\nUn funnel a due assi.\n\n## Acceptance criteria\n\n- [ ] Deterministico."


def test_file_toccati_elenca_tutti_i_percorsi():
    diff = _hunk("src/a.py", 3) + _hunk("docs/evidence/dossier/2026-09-01.json", 5)

    assert file_toccati(diff) == ["src/a.py", "docs/evidence/dossier/2026-09-01.json"]


def test_filtra_via_i_file_di_dati():
    """La forma di PR #477: il dossier generato domina il diff."""
    diff = _hunk("scripts/misura.py", 10) + _hunk("docs/evidence/dossier/2026-09-01.json", 5000)

    filtrato = filtra_diff(diff)

    assert "scripts/misura.py" in filtrato
    assert "dossier/2026-09-01.json" not in filtrato
    assert len(filtrato) < len(diff) / 10


def test_filtra_via_i_test():
    diff = _hunk("src/a.py", 5) + _hunk("tests/test_a.py", 5)

    filtrato = filtra_diff(diff)

    assert "src/a.py" in filtrato
    assert "tests/test_a.py" not in filtrato


def test_diff_di_soli_dati_non_produce_prompt():
    diff = _hunk("docs/evidence/dossier/2026-09-01.json", 100)

    assert costruisci_prompt(diff, ISSUE) == []


def test_diff_sotto_il_tetto_resta_un_prompt_unico():
    """Sotto il tetto si conserva la visione d'insieme.

    Il rilievo migliore prodotto su PR #472 — la contraddizione fra il commento
    di funnel.py:88 e l'ordine di valutazione reale — richiedeva di vedere il
    modulo intero.
    """
    diff = _hunk("src/a.py", 20) + _hunk("src/b.py", 20)

    prompt = costruisci_prompt(diff, ISSUE)

    assert len(prompt) == 1
    assert "src/a.py" in prompt[0]
    assert "src/b.py" in prompt[0]


def test_diff_sopra_il_tetto_si_spezza_per_file():
    diff = _hunk("src/a.py", 400) + _hunk("src/b.py", 400)

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=5_000)

    assert len(prompt) == 2
    assert "src/a.py" in prompt[0] and "src/b.py" not in prompt[0]
    assert "src/b.py" in prompt[1] and "src/a.py" not in prompt[1]


def test_ogni_prompt_porta_la_issue_e_lo_schema():
    diff = _hunk("src/a.py", 400) + _hunk("src/b.py", 400)

    prompt = costruisci_prompt(diff, ISSUE, tetto_byte=5_000)

    for singolo in prompt:
        assert "Acceptance criteria" in singolo
        assert "scenario_di_fallimento" in singolo
        assert "ramo_irraggiungibile" in singolo
        assert "mascherato_da" in singolo


def test_il_prompt_chiede_di_non_approvare():
    """Il compito e' trovare difetti, non dare un verdetto."""
    prompt = costruisci_prompt(_hunk("src/a.py", 10), ISSUE)

    assert "NON e' approvare" in prompt[0]
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/review_locale/test_estrazione.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.review_locale.estrazione'`

- [ ] **Step 3: Scrivi l'implementazione minima**

`src/review_locale/estrazione.py`:

```python
"""Filtro del diff e costruzione dei prompt per il modello locale.

Modulo puro: riceve il testo del diff e il corpo della issue, non chiama `gh`.

Il filtro non e' un dettaglio di efficienza, e' cio' che rende esaminabili le PR
di questo repo. PR #477 porta +69.343 righe di cui 58.339 sono un dossier JSON
generato: senza filtro sarebbe trenta volte oltre il contesto del modello e
verrebbe saltata, con il filtro il codice vero (~2.000 righe) ci sta comodo.

I test sono esclusi dal diff dato al modello: il compito e' giudicare il codice
contro la issue, e i test consumano contesto senza aggiungere ipotesi.
"""

from __future__ import annotations

import re


ESTENSIONI_CODICE = (".py", ".sh", ".sql")

# 35 KB: il run riuscito su PR #472 aveva un prompt da 42 KB comprensivo di
# issue e schema, quindi il diff sotto i 35 KB tiene il caso normale in un
# prompt unico.
TETTO_BYTE = 35_000

_INIZIO_FILE = re.compile(r"^diff --git a/(\S+) b/\S+", re.MULTILINE)

_INTESTAZIONE = """Sei un ingegnere senior che fa la review di una pull request su un sistema di
trading in Python. Ricevi il testo della issue che la PR dichiara di chiudere e il
diff del codice di produzione (i file di test sono esclusi). NON hai accesso al
repository: usa soltanto cio' che segue.

Il tuo compito **NON e' approvare**. Il tuo compito e' trovare i difetti. Se non
trovi nulla di concreto dillo, ma non inventare rilievi per riempire lo spazio:
ogni rilievo deve essere qualcosa su cui un manutentore agirebbe.

Cerca in particolare, in ordine di gravita':
1. RAMI IRRAGGIUNGIBILI: codice o categorie che la logica a monte non puo' mai
   produrre (e i test che li esercitano con input impossibili).
2. CLASSIFICAZIONI SBAGLIATE: un caso che finisce nella categoria di un altro,
   per una condizione troppo larga o troppo stretta.
3. EVIDENZE FALSE: un campo che afferma un fatto che non e' stato osservato.
4. DOPPI CONTEGGI o predicati riscritti due volte che possono divergere.
5. NON DETERMINISMO: valori letti a run time invece che dallo stato del giorno
   analizzato.
6. SCARTI FRA CIO' CHE LA ISSUE CHIEDE E CIO' CHE IL DIFF FA, incluse le
   contraddizioni fra un commento o una docstring e il codice che descrive.

Alcuni difetti si mascherano a vicenda: un ramo che svuota una popolazione rende
irraggiungibili i difetti a valle. Se te ne accorgi, dillo in `mascherato_da`.
"""

_SCHEMA = """
## COSA DEVI PRODURRE

Rispondi con UN SOLO oggetto JSON valido, senza testo prima o dopo:

{
  "rilievi": [
    {
      "gravita": "<ALTA|MEDIA|BASSA>",
      "categoria": "<ramo_irraggiungibile|classificazione_sbagliata|evidenza_falsa|doppio_conteggio|non_determinismo|scarto_dalla_issue>",
      "posizione": "<file:riga come compare nel diff>",
      "difetto": "<una frase: cosa e' sbagliato>",
      "scenario_di_fallimento": "<input o stato concreto -> risultato sbagliato. Uno scenario, non una preoccupazione generica>",
      "mascherato_da": "<il rilievo che oggi lo rende irraggiungibile, oppure null>"
    }
  ],
  "verificato_e_scartato": ["<cose che hai controllato e che ti sembrano corrette>"],
  "criteri_issue": [
    {"criterio": "<il criterio di accettazione, copiato>", "esito": "<SODDISFATTO|NON_SODDISFATTO|PARZIALE>", "perche": "<una frase>"}
  ],
  "informazioni_mancanti": ["<cio' che ti servirebbe e non hai>"],
  "confidenza": <numero fra 0 e 1>
}
"""


def file_toccati(diff: str) -> list[str]:
    """I percorsi che il diff modifica, nell'ordine in cui compaiono."""
    return _INIZIO_FILE.findall(diff)


def _blocchi(diff: str) -> list[tuple[str, str]]:
    """Il diff spezzato in (percorso, testo del blocco)."""
    posizioni = [(m.group(1), m.start()) for m in _INIZIO_FILE.finditer(diff)]
    risultato = []
    for indice, (percorso, inizio) in enumerate(posizioni):
        fine = posizioni[indice + 1][1] if indice + 1 < len(posizioni) else len(diff)
        risultato.append((percorso, diff[inizio:fine]))
    return risultato


def _e_codice(percorso: str) -> bool:
    if percorso.startswith("tests/") or "/tests/" in percorso:
        return False
    return percorso.endswith(ESTENSIONI_CODICE)


def filtra_diff(diff: str) -> str:
    """Il diff ridotto ai soli file di codice di produzione."""
    return "".join(testo for percorso, testo in _blocchi(diff) if _e_codice(percorso))


def _prompt(diff: str, issue: str) -> str:
    return (
        f"{_INTESTAZIONE}\n"
        f"## ISSUE COLLEGATA\n\n{issue}\n\n"
        f"## DIFF DEL CODICE DI PRODUZIONE\n\n{diff}\n"
        f"{_SCHEMA}"
    )


def costruisci_prompt(diff: str, issue: str, tetto_byte: int = TETTO_BYTE) -> list[str]:
    """Uno o piu' prompt pronti da mandare al modello.

    Sotto il tetto: un prompt unico, che conserva la visione d'insieme. Sopra:
    un prompt per file di codice, perche' una PR troppo grande esaminata a
    pezzi vale piu' di una PR saltata.
    """
    blocchi = [(percorso, testo) for percorso, testo in _blocchi(diff) if _e_codice(percorso)]
    if not blocchi:
        return []

    intero = "".join(testo for _, testo in blocchi)
    if len(intero) <= tetto_byte:
        return [_prompt(intero, issue)]
    return [_prompt(testo, issue) for _, testo in blocchi]
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/review_locale/test_estrazione.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Verifica il filtro sul caso reale che lo motiva**

Run:
```bash
gh pr diff 477 > /tmp/pr477.diff
.venv/bin/python -c "
from src.review_locale.estrazione import filtra_diff, file_toccati
d = open('/tmp/pr477.diff').read()
f = filtra_diff(d)
print('diff intero:', len(d), 'byte,', len(file_toccati(d)), 'file')
print('filtrato:   ', len(f), 'byte,', len(file_toccati(f)), 'file')
"
```
Expected: il diff intero è ~2 MB su 9 file; il filtrato deve scendere sotto i 100 KB e contenere solo i `.py` non di test (`scripts/s4_cluster_literature.py`, `scripts/measure_169_dedup_rules.py`).

Se il filtrato resta sopra i 35 KB, è il caso previsto: `costruisci_prompt` spezzerà per file. Nessuna azione.

- [ ] **Step 6: Commit**

```bash
git add src/review_locale/estrazione.py tests/review_locale/test_estrazione.py
git commit -m "feat(review-locale): filtro del diff e costruzione dei prompt

Il filtro ai file di codice e' cio' che rende esaminabili le PR di questo
repo: #477 porta 69k righe di cui 58k sono un dossier generato. Sotto i 35 KB
un prompt unico che conserva la visione d'insieme, sopra un prompt per file."
```

---

### Task 5: orchestratore

**Files:**
- Create: `scripts/review_notturna_locale.py`
- Test: `tests/scripts/test_review_notturna_locale.py`

`pytest.ini` ha `pythonpath = scripts`, quindi il test importa `review_notturna_locale` direttamente.

- [ ] **Step 1: Scrivi il test che fallisce**

`tests/scripts/test_review_notturna_locale.py`:

```python
"""Orchestratore della review notturna: integrazione con gh e server finti."""

import json

import pytest

import review_notturna_locale as orch


_RILIEVO = {
    "gravita": "ALTA",
    "categoria": "non_determinismo",
    "posizione": "src/x.py:10",
    "difetto": "soglia letta a run time",
    "scenario_di_fallimento": "rieseguire il giorno 08-25 riclassifica BELOW_GATE",
    "mascherato_da": None,
}


class _Finti:
    """Registra le chiamate esterne invece di eseguirle."""

    def __init__(self, risposta: str):
        self.risposta = risposta
        self.commenti: list[tuple[int, str]] = []
        self.ledger: list[dict] = []
        self.server_avviato = 0
        self.server_fermato = 0


@pytest.fixture
def finti(monkeypatch):
    f = _Finti(risposta=json.dumps({"rilievi": [_RILIEVO]}))

    monkeypatch.setattr(orch, "avvia_server", lambda: f.__setattr__("server_avviato", f.server_avviato + 1))
    monkeypatch.setattr(orch, "ferma_server", lambda: f.__setattr__("server_fermato", f.server_fermato + 1))
    monkeypatch.setattr(orch, "pr_aperte", lambda: [orch.PrCandidata(472, "bbb", "2026-09-02T08:00:00Z")])
    monkeypatch.setattr(orch, "diff_pr", lambda numero: (
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n@@ -0,0 +1,1 @@\n+x = 1\n"
    ))
    monkeypatch.setattr(orch, "issue_della_pr", lambda numero: "## Acceptance criteria\n- [ ] Deterministico.")
    monkeypatch.setattr(orch, "leggi_ledger", lambda: f.ledger)
    monkeypatch.setattr(orch, "scrivi_ledger", lambda voce: f.ledger.append(voce))
    monkeypatch.setattr(orch, "pubblica_commento", lambda numero, corpo: f.commenti.append((numero, corpo)))
    monkeypatch.setattr(orch, "interroga_modello", lambda prompt: (f.risposta, "ragionamento", 1000))
    return f


def test_referto_con_rilievi_pubblica_e_registra(finti):
    codice = orch.main([])

    assert codice == 0
    assert len(finti.commenti) == 1
    numero, corpo = finti.commenti[0]
    assert numero == 472
    assert "soglia letta a run time" in corpo
    assert finti.ledger[-1]["stato"] == "ESAMINATA_CON_RILIEVI"


def test_il_commento_dichiara_l_origine(finti):
    """Chi legge deve poter pesare i rilievi sapendo da dove vengono."""
    orch.main([])

    _, corpo = finti.commenti[0]
    assert "modello locale" in corpo
    assert "non verificat" in corpo


def test_referto_senza_rilievi_non_pubblica(finti):
    finti.risposta = json.dumps({"rilievi": []})

    codice = orch.main([])

    assert codice == 0
    assert finti.commenti == []
    assert finti.ledger[-1]["stato"] == "ESAMINATA_SENZA_RILIEVI"


def test_json_invalido_non_pubblica(finti):
    finti.risposta = "{non e' JSON"

    codice = orch.main([])

    assert codice == 0
    assert finti.commenti == []
    assert finti.ledger[-1]["stato"] == "NON_ESAMINATA"


def test_le_assoluzioni_non_raggiungono_il_commento(finti):
    """Il principio della spec, verificato end-to-end."""
    finti.risposta = json.dumps({
        "rilievi": [_RILIEVO],
        "verificato_e_scartato": ["La SQL esclude correttamente SKIP_THRESHOLD"],
    })

    orch.main([])

    _, corpo = finti.commenti[0]
    assert "verificato_e_scartato" not in corpo
    assert "SKIP_THRESHOLD" not in corpo


def test_nessuna_pr_eleggibile_non_accende_il_server(finti, monkeypatch):
    monkeypatch.setattr(orch, "pr_aperte", lambda: [])

    codice = orch.main([])

    assert codice == 0
    assert finti.server_avviato == 0
    assert finti.commenti == []


def test_il_server_viene_sempre_fermato(finti):
    finti.risposta = "{non e' JSON"

    orch.main([])

    assert finti.server_avviato == 1
    assert finti.server_fermato == 1
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `.venv/bin/python -m pytest tests/scripts/test_review_notturna_locale.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'review_notturna_locale'`

- [ ] **Step 3: Scrivi l'implementazione minima**

`scripts/review_notturna_locale.py`:

```python
"""Review notturna di una PR aperta sul worker locale (spec 2026-09-03).

Orchestratore: tutto l'impuro vive qui — systemctl, gh, la chiamata HTTP in
streaming, il ledger. La logica sta nei moduli puri di `src/review_locale/`.

Il job non ha alcun potere sul merge: pubblica rilievi e nient'altro. Il modello
e' una lente che esamina, mai un cancello che approva — su PR #472 ha prodotto
undici assoluzioni di cui almeno due false, e false esattamente sui due punti
dove i difetti erano reali.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

import httpx

from src.review_locale.estrazione import costruisci_prompt
from src.review_locale.referto import NON_VALIDO, PUBBLICABILE, SENZA_RILIEVI, prepara
from src.review_locale.rilevatori import e_corsa_condannata, e_loop, misura_ripetizione
from src.review_locale.selezione import PrCandidata, scegli

log = logging.getLogger("review_notturna")

LEDGER = Path("/home/stefano/llm/notte/ledger.jsonl")
DIAGNOSI = Path("/home/stefano/llm/notte")
UNIT = "llama-server.service"
BASE_URL = "http://127.0.0.1:8080"
MODELLO = "qwen3.8-27b-local"
MAX_TOKENS = 32_768
# 9 ore: piu' del tetto teorico (32.768 token a ~1,1 tok/s), cosi' il limite lo
# pongono i rilevatori e non il client.
TIMEOUT_HTTP = 32_400

# Nel ledger lo stato di un tentativo fallito e' NON_ESAMINATA, distinto dallo
# stato NON_VALIDO che il modulo `referto` usa per il singolo referto: sono due
# cose diverse — un referto invalido e un tentativo che non ha prodotto nulla.
NON_VALIDO_LEDGER = "NON_ESAMINATA"

INTESTAZIONE_COMMENTO = """## Rilievi da una review sul modello locale

Prodotti da un worker locale (Qwen3.8-27B) su questa PR contro la issue che dichiara di
chiudere. **Non sono verificati da nessuno**: il modello e' affidabile quando trova un
difetto che esiste e inaffidabile quando dichiara corretto cio' che ha guardato, quindi
questi rilievi vanno letti come piste da controllare, non come fatti accertati.

Questo commento non esprime nessun verdetto sul merge.

---

"""


# --- confini esterni ------------------------------------------------------


def avvia_server() -> None:
    subprocess.run(["systemctl", "--user", "start", UNIT], check=True)
    for _ in range(60):
        try:
            if httpx.get(f"{BASE_URL}/health", timeout=5).json().get("status") == "ok":
                return
        except Exception:  # noqa: BLE001 — il server sta ancora salendo
            pass
        time.sleep(5)
    raise RuntimeError("il server locale non ha risposto a /health entro 5 minuti")


def ferma_server() -> None:
    subprocess.run(["systemctl", "--user", "stop", UNIT], check=False)


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def pr_aperte() -> list[PrCandidata]:
    righe = json.loads(_gh("pr", "list", "--state", "open", "--json", "number,headRefOid,createdAt"))
    return [
        PrCandidata(numero=r["number"], sha=r["headRefOid"], creata_il=r["createdAt"])
        for r in righe
    ]


def diff_pr(numero: int) -> str:
    return _gh("pr", "diff", str(numero))


def issue_della_pr(numero: int) -> str:
    """Il corpo della issue che la PR dichiara di chiudere.

    Si legge dal corpo della PR (`Closes #N` / `Part of #N`). Senza issue
    collegata si restituisce il corpo della PR: e' comunque la dichiarazione di
    intenti contro cui giudicare il diff.
    """
    corpo = json.loads(_gh("pr", "view", str(numero), "--json", "body"))["body"] or ""
    for marcatore in ("Closes #", "closes #", "Part of #", "part of #"):
        if marcatore in corpo:
            numero_issue = corpo.split(marcatore, 1)[1].split()[0].strip(".,;:")
            if numero_issue.isdigit():
                return json.loads(
                    _gh("issue", "view", numero_issue, "--json", "body")
                )["body"] or corpo
    return corpo


def pubblica_commento(numero: int, corpo: str) -> None:
    subprocess.run(
        ["gh", "pr", "comment", str(numero), "--body", corpo], check=True
    )


def leggi_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(riga) for riga in LEDGER.read_text().splitlines() if riga.strip()]


def scrivi_ledger(voce: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")


def interroga_modello(prompt: str) -> tuple[str, str, int]:
    """Manda il prompt e restituisce (content, reasoning, token generati).

    Interrompe se i rilevatori riconoscono un loop o una corsa che non puo' piu'
    chiudere. In quel caso `content` e' vuoto e il chiamante non pubblica nulla.
    """
    richiesta = {
        "model": MODELLO,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning_effort": "medium",
        "temperature": 1.0, "top_p": 0.95, "top_k": 20,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "stream": True,
    }
    content: list[str] = []
    reasoning: list[str] = []
    generati = 0
    ultimo_controllo = 0

    with httpx.stream(
        "POST", f"{BASE_URL}/v1/chat/completions",
        json=richiesta,
        headers={"Authorization": "Bearer not-needed"},
        timeout=TIMEOUT_HTTP,
    ) as risposta:
        for riga in risposta.iter_lines():
            if not riga.startswith("data: "):
                continue
            payload = riga[6:].strip()
            if payload == "[DONE]":
                break
            try:
                dato = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for scelta in dato.get("choices") or []:
                delta = scelta.get("delta") or {}
                if delta.get("content"):
                    content.append(delta["content"])
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
            generati += 1

            if generati - ultimo_controllo >= 500:
                ultimo_controllo = generati
                testo = "".join(reasoning)
                misure = misura_ripetizione(testo)
                log.info("token=%d misure=%s", generati, misure)
                if e_loop(misure):
                    log.error("loop rilevato a %d token: interrompo", generati)
                    return "", testo, generati
                if e_corsa_condannata(generati, content_vuoto=not content):
                    log.error("corsa condannata a %d token: interrompo", generati)
                    return "", testo, generati

    return "".join(content), "".join(reasoning), generati


# --- composizione ---------------------------------------------------------


def _corpo_commento(rilievi: Sequence[dict]) -> str:
    pezzi = [INTESTAZIONE_COMMENTO]
    for rilievo in rilievi:
        pezzi.append(
            f"### {rilievo['gravita']} — {rilievo['categoria']}\n\n"
            f"**{rilievo['posizione']}**\n\n"
            f"{rilievo['difetto']}\n\n"
            f"**Scenario:** {rilievo['scenario_di_fallimento']}\n"
        )
        if rilievo.get("mascherato_da"):
            pezzi.append(f"\n**Mascherato da:** {rilievo['mascherato_da']}\n")
        pezzi.append("\n")
    return "".join(pezzi)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pr", type=int, help="esamina questa PR invece di scegliere dal ledger")
    args = ap.parse_args(argv)

    candidate = pr_aperte()
    if args.pr is not None:
        candidate = [pr for pr in candidate if pr.numero == args.pr]
    scelta = scegli(candidate, leggi_ledger())
    if scelta is None:
        log.info("nessuna PR eleggibile: niente da fare")
        return 0

    log.info("PR scelta: #%d (%s)", scelta.numero, scelta.sha[:8])
    prompt = costruisci_prompt(diff_pr(scelta.numero), issue_della_pr(scelta.numero))
    if not prompt:
        scrivi_ledger({
            "pr": scelta.numero, "sha": scelta.sha,
            "stato": NON_VALIDO_LEDGER, "causa": "nessun file di codice nel diff",
            "iniziato": datetime.now().astimezone().isoformat(),
        })
        return 0

    iniziato = datetime.now().astimezone()
    avvia_server()
    try:
        rilievi: list[dict] = []
        stato = SENZA_RILIEVI
        causa = None
        misure = {}
        for indice, singolo in enumerate(prompt):
            log.info("prompt %d/%d, %d byte", indice + 1, len(prompt), len(singolo))
            content, reasoning, generati = interroga_modello(singolo)
            misure = misura_ripetizione(reasoning)
            (DIAGNOSI / f"ragionamento_pr{scelta.numero}_{indice}.txt").write_text(reasoning)
            esito = prepara(content)
            if esito.stato == PUBBLICABILE:
                rilievi.extend(esito.rilievi)
                stato = "ESAMINATA_CON_RILIEVI"
            elif esito.stato == NON_VALIDO and stato == SENZA_RILIEVI:
                stato, causa = NON_VALIDO_LEDGER, esito.causa

        if rilievi:
            stato = "ESAMINATA_CON_RILIEVI"
            pubblica_commento(scelta.numero, _corpo_commento(rilievi))
        elif stato == SENZA_RILIEVI:
            stato = "ESAMINATA_SENZA_RILIEVI"
    finally:
        ferma_server()

    scrivi_ledger({
        "pr": scelta.numero, "sha": scelta.sha,
        "iniziato": iniziato.isoformat(),
        "concluso": datetime.now().astimezone().isoformat(),
        "stato": stato, "causa": causa,
        "rilievi": len(rilievi),
        "misure_loop": misure,
    })
    log.info("esito: %s (%d rilievi)", stato, len(rilievi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `.venv/bin/python -m pytest tests/scripts/test_review_notturna_locale.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Esegui tutta la suite dei moduli nuovi**

Run: `.venv/bin/python -m pytest tests/review_locale/ tests/scripts/test_review_notturna_locale.py -v`
Expected: PASS, 38 passed

**Non** lanciare la suite intera: in CI è cronicamente rossa per motivi ambientali (integration test senza DB) e il rumore coprirebbe il segnale.

- [ ] **Step 6: Commit**

```bash
git add scripts/review_notturna_locale.py tests/scripts/test_review_notturna_locale.py
git commit -m "feat(review-locale): orchestratore della review notturna

Tutto l'impuro in un posto: systemctl, gh, streaming httpx, ledger. I
rilevatori girano ogni 500 token sullo stream. Il test di integrazione verifica
end-to-end che un referto non pubblicabile non produca alcuna chiamata a
gh pr comment, e che le assoluzioni non raggiungano il commento."
```

---

### Task 6: unit systemd e prova a secco

**Files:**
- Create: `~/.config/systemd/user/review-notturna-locale.service` (fuori dal repo)
- Create: `~/.config/systemd/user/review-notturna-locale.timer` (fuori dal repo)

- [ ] **Step 1: Scrivi le unit**

`~/.config/systemd/user/review-notturna-locale.service`:

```ini
[Unit]
Description=Review notturna di una PR aperta sul worker locale
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/stefano/Documents/Projects/Alembic
ExecStart=/home/stefano/Documents/Projects/Alembic/.venv/bin/python \
  /home/stefano/Documents/Projects/Alembic/scripts/review_notturna_locale.py
StandardOutput=append:/home/stefano/llm/notte/review_notturna.log
StandardError=append:/home/stefano/llm/notte/review_notturna.log
# Nessun TimeoutStartSec: il limite lo pongono i rilevatori, non l'orologio.
TimeoutStartSec=infinity
```

`~/.config/systemd/user/review-notturna-locale.timer`:

```ini
[Unit]
Description=Review notturna sul worker locale, ogni notte all'01:07

[Timer]
# 01:07 sta nel buco fra il giro del loop roadmap delle 23:00 e quello delle
# 07:00. Il minuto spostato evita di accodarsi a tutto cio' che parte allo
# scoccare dell'ora.
OnCalendar=*-*-* 01:07:00
Persistent=false

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Prova a secco su una PR reale, senza pubblicare**

Prima di armare il timer, verifica la catena esterna senza toccare GitHub. Il modello **non** viene interrogato: si controlla solo che selezione, diff, issue e prompt si costruiscano.

Run:
```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -c "
import review_notturna_locale as o
from src.review_locale.estrazione import costruisci_prompt
from src.review_locale.selezione import scegli
scelta = scegli(o.pr_aperte(), o.leggi_ledger())
print('scelta:', scelta)
p = costruisci_prompt(o.diff_pr(scelta.numero), o.issue_della_pr(scelta.numero))
print('prompt:', len(p), 'pezzi,', [len(x) for x in p], 'byte')
print(p[0][:400])
"
```
Expected: stampa la PR più vecchia fra le aperte, il numero di prompt e le dimensioni. Il primo prompt inizia con «Sei un ingegnere senior…» e contiene i criteri di accettazione della issue.

- [ ] **Step 3: Arma il timer**

Run:
```bash
systemctl --user daemon-reload
systemctl --user enable --now review-notturna-locale.timer
systemctl --user list-timers review-notturna-locale --all
```
Expected: la riga del timer mostra `NEXT` alla prossima 01:07.

- [ ] **Step 4: Commit delle unit come copia versionata**

Le unit vivono in `~/.config`, ma una copia nel repo le rende ricostruibili.

```bash
mkdir -p deploy/systemd
cp ~/.config/systemd/user/review-notturna-locale.service deploy/systemd/
cp ~/.config/systemd/user/review-notturna-locale.timer deploy/systemd/
git add deploy/systemd/review-notturna-locale.service deploy/systemd/review-notturna-locale.timer
git commit -m "chore(review-locale): unit systemd del job notturno

Copia versionata di cio' che vive in ~/.config/systemd/user/: il timer gira
all'01:07, nel buco fra i giri del loop roadmap delle 23 e delle 7, e il
service non ha TimeoutStartSec perche' il limite lo pongono i rilevatori."
```

---

### Task 7: primo referto reale e apertura della PR

- [ ] **Step 1: Esegui il job a mano su una PR scelta**

Run: `.venv/bin/python scripts/review_notturna_locale.py --pr 478`
Expected: 3-4 ore. Il log mostra una riga `token=… misure=…` ogni 500 token; alla fine `esito: …`.

Questo è il primo referto prodotto dalla catena completa, ed è anche la prova che il commento pubblicato ha la forma giusta.

- [ ] **Step 2: Controlla il ledger**

Run: `tail -1 /home/stefano/llm/notte/ledger.jsonl | .venv/bin/python -m json.tool`
Expected: una voce con `stato`, `rilievi`, `misure_loop` popolati e `concluso` valorizzato.

- [ ] **Step 3: Apri la PR**

```bash
git push -u origin <branch>
gh pr create --base main \
  --title "feat: review notturna delle PR sul worker locale" \
  --body "$(cat <<'CORPO'
Implementa la spec `docs/superpowers/specs/2026-09-03-review-notturna-locale-design.md`.

Una volta a notte all'01:07 il worker locale Qwen3.8-27B esamina una PR aperta contro la
issue che dichiara di chiudere, e i soli rilievi vengono pubblicati come commento.

Il disegno e' costruito intorno a una asimmetria misurata nei quattro probe del 01-02/09
piu' il run completo su PR #472: su un difetto che esiste il modello e' eccellente (9/9,
7/7, 6/7), su un difetto che non esiste e' inaffidabile — ha fallito il controllo negativo
#324 e su #472 ha prodotto undici assoluzioni di cui almeno due false, false esattamente
sui due punti dove i difetti erano reali. Da qui: il campo `verificato_e_scartato` non
viene pubblicato mai, un referto senza rilievi non produce commento, e il job non ha
alcun potere sul merge.

Il limite non e' un orologio ma due rilevatori su cio' che il modello produce: ripetizione
di 12-grammi per il loop vero, e ragionamento a 28.000 token con content vuoto per la
corsa aritmeticamente incapace di chiudere.

**Come si verifica:**

```
.venv/bin/python -m pytest tests/review_locale/ tests/scripts/test_review_notturna_locale.py -v
```

38 test verdi. Il test che protegge il principio e'
`test_le_assoluzioni_non_raggiungono_il_commento`: verifica end-to-end che
`verificato_e_scartato` non compaia nel corpo del commento.

Primo referto reale prodotto su PR #478 (vedi il commento sulla PR e la voce nel ledger).

**Freeze #171:** strumentazione e misura, nessuna taratura toccata.

Part of #21.
CORPO
)"
```

- [ ] **Step 4: Non mergiare**

Il merge è dell'operatore.

---

## Autoreview

**Copertura della spec.** §2 (misura e principio) → Task 1 e il test end-to-end di Task 5. §3 destinazione → Task 5 `pubblica_commento` + intestazione. §3 rapporto col loop → nessun task tocca `roadmap_agent_loop.sh`, per costruzione. §3 selezione → Task 3. §3 sede del codice → tutti i task nel repo. §3 ledger fuori da git → Task 5, `LEDGER` sotto `/home/stefano/llm/notte/`. §4 architettura → Task 1-5 nell'ordine dei moduli. §5 rilevatori → Task 2 + il loro innesto nello stream in Task 5. §6 errori: JSON invalido → Task 1 e 5; loop/corsa condannata → Task 2 e 5; server non parte → `avvia_server` solleva e il `finally` ferma il server; nessuna PR eleggibile → Task 5 test dedicato; `gh` fallisce → `check=True` propaga e il `finally` spegne. §7 dati → Task 5 `scrivi_ledger`. §8 test → Task 1-5. §9 cosa non fa → nessun task aggiunge label, `blocked_by` o verdetti.

**Una riparazione del JSON invalido non è implementata.** La spec la prevede (una richiesta sola, col vincolo del `NODE_CONTRACT`). L'ho lasciata fuori di proposito: costerebbe altre 3-4 ore di macchina su un referto già sospetto, e con `response_format: json_object` imposto dal server il JSON invalido dovrebbe essere raro. Il ledger registra `NON_ESAMINATA` e lo sha torna eleggibile domani, quindi il caso è coperto senza il ritentativo. **Se dopo qualche settimana il ledger mostrasse `NON_ESAMINATA` frequenti per JSON invalido, allora vale implementarla** — e a quel punto sui dati, non a priori.

**Coerenza dei nomi.** `prepara`/`Esito`/`PUBBLICABILE`/`SENZA_RILIEVI`/`NON_VALIDO` (Task 1) usati identici in Task 5. `misura_ripetizione`/`e_loop`/`e_corsa_condannata` (Task 2) idem. `PrCandidata(numero, sha, creata_il)` e `scegli` (Task 3) idem. `costruisci_prompt`/`filtra_diff`/`file_toccati` (Task 4) idem. Attenzione a una collisione voluta: `NON_VALIDO` è lo stato del *referto*, `NON_ESAMINATA` (`NON_VALIDO_LEDGER`) è lo stato del *tentativo* nel ledger — sono due cose diverse e il commento nel codice lo dice.

**Nessun segnaposto:** ogni step che cambia codice porta il codice, ogni comando porta l'output atteso.
