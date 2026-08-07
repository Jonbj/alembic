# S7 — 07 Bug

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift) — RIMOSSA
**Data:** 2026-08-04
**Metodo:** ogni bug confermato da repro eseguito o traccia deterministica
(DB read-only). Nessun bug asserito senza conferma. S7 è **rimossa** con
**zero ordini lifecycle** → non ci sono bug di **path live** (mai esistito).
I "bug" sono **gap di integrazione upstream** e **configurazione debole**, non
difetti di logica S7.

## Riepilogo

| ID | Severità | Tipo | Luogo (git `1dd2c35`) | Conferma |
|---|---|---|---|---|
| **BUG-A** | HIGH (operatività) | carburante zero | `pead.py:17` (surprise opzionale) + `signal.py:42` (gate reject-None) + ALPHA-A2 mai wired | repro_1 ESEGUITO |
| **BUG-B** | HIGH (validità fenomeno) | universo competuto | design ALPHA-A5 large-cap vs fenomeno vivo small-cap | traccia lifecycle doc + letteratura (fase 03) |
| **BUG-C** | MEDIUM (forma debole) | long-only + polarity + hold 20d | `strategy.py:51` (beat-only), `pead.py` (polarity), `strategy.py:18` (hold 20d) | traccia statica (fase 05 DV-S7-3/4/5) |
| **BUG-D** | LOW (persistenza) | table mai materializzata | `pead_signals` (DDL solo doc, nessuna migration) | traccia DB `\d pead_signals` (inesistente) |
| **OBS-1** | osservazione positiva | guard anti-reintro viva | `tests/test_p0_13_strategy_containment.py:62-97` | repro_2 ESEGUITO |

---

## BUG-A — Carburante zero: consensus mai wired → zero ordini (HIGH, operatività)

**Luoghi:** `src/models/pead.py:17` (`surprise_pct: float | None = None`),
`src/strategies/s7/signal.py:42` (`if surprise is None: return None`),
ALPHA-A2 (consensus provider esterno) **mai wired** (lifecycle doc).

**Descrizione:** il design dichiarava surprise da consensus esterno (ALPHA-A2:
Zacks/Refinitiv/FMP). Il codice dichiara `surprise_pct` **opzionale** (`None` ok),
popolato dall'LLM parsing dell'8-K. Il gate `signal.py:42` rejecta ogni segnale
con `surprise_pct is None`. Poiché ALPHA-A2 **non è mai stato wired**, e l'LLM
spesso non estrae surprise dal testo (o estrae null), `surprise_pct` resta
`None` → il gate rejecta **tutti** i segnali → **zero ordini lifecycle**.

Questo **non è un bug di logica S7** (i gate sono corretti e difensivi) ma un
**gap di integrazione upstream**: il consensus provider non è mai stato
connesso, quindi il campo opzionale resta spesso None. È la **causa
strutturale del "mai live"**.

**Conferma (repro_1, statica deterministica, ESEGUITO):**
```
src/models/pead.py exists in working tree: False   (rimosso d1e6de6)
src/strategies/s7/signal.py exists in working tree: False
surprise_pct is Optional (pead.py:17): True
gate rejects surprise=None (signal.py:42): True
consensus provider wired (ALPHA-A2): False
=> CARBURANTE ZERO: True
CONFIRMED
```

**Impatto:** S7 non ha mai avuto carburante. Per un revival, ALPHA-A2 deve
essere wired **prima** di qualunque test — altrimenti i gate filtrano tutto.

**Nota:** il repro è statico (i file sono rimossi) MA la logica è verificata
dal commit `1dd2c35` (fase 05) e dal lifecycle doc. La conferma deterministica
è il ragionamento: `Optional(None) + gate-reject-None + consensus-not-wired →
zero-segnali`. È una catena logica deterministica, non un'asserzione.

## BUG-B — Universo competuto: large-cap dove PEAD è morto (HIGH, validità)

**Luogo:** design ALPHA-A5 (large-cap), POC-1 small/mid fallito per copertura
IEX insufficiente (lifecycle doc §3).

**Descrizione:** la letteratura (fase 03) indica PEAD vivo su **small-cap**
(net 3.8%, Quant Decoded 2025) e **competuto su large-cap** (morto dal 2006,
Martineau 2021; drift near-zero, Chordia 2009). S7 era configurata su
**large-cap ALPHA-A5** — l'universo competuto. POC-1 small/mid (dove l'edge
vivo) è fallito per **copertura IEX insufficiente** (n=15 < 30).

**Conferma (traccia lifecycle + letteratura):**
- ALPHA-A5 large-cap FAIL: drift=beta SPY, hit 51%<55%, no dose-response, n=76
- POC-1 small/mid INCONCLUSIVE_DATA: n=15, copertura insufficiente
- Quant Decoded 2025: net drift large-cap 1.6% vs small-cap 3.8%

**Impatto:** anche se il carburante (BUG-A) fosse stato wired, l'universo
large-cap avrebbe prodotto drift≈beta (non alpha). L'universo è la **causa
strutturale del FAIL numerico** (ALPHA-A5). Per un revival, spostarsi su
small/mid — MA richiede copertura dati che il progetto non ha (IEX
insufficiente). Bug di **configurazione/design**, non di codice.

## BUG-C — Forma debole: long-only + polarity + hold 20d (MEDIUM, forma)

**Luoghi:** `src/strategies/s7/strategy.py:51` (`s.direction == "beat"` long-only),
`src/models/pead.py:10-21` (polarity-strutturato, no embedding),
`src/strategies/s7/strategy.py:18` (`hold_days: int = 20`).

**Descrizione:** S7 implementa la **combinazione specificamente debole** del
PEAD/tone su tre dimensioni (DV-S7-3/4/5):
1. **Long-only beat** (`strategy.py:51`) — PEAD canonico simmetrico; la gamba
   long-only positiva è la **debole** (Druz 2015: negatività predice più forte).
2. **Polarity sentiment** (`pead.py` campi strutturati discreti, no embedding) —
   la letteratura (Chung 2023) indica edge tone vivo con **embedding contestuali**
   (SBERT), non polarity (che decade OOS post-2020).
3. **Hold 20d** (`strategy.py:18`) — la letteratura tone (Hameleers 2025)
   indica edge vivo a **5-10g** (Sharpe>1), decade a 20g.

**Conferma (traccia statica, fase 05 DV-S7-3/4/5):**
- `strategy.py:51` filtro `direction == "beat"` → long-only ✓
- `pead.py:10-21` campi discreti (direction, surprise_pct, confidence) →
  polarity, no embedding ✓
- `strategy.py:18` `hold_days: int = 20` → orizzonte oltre il decay tone ✓
- POC-2 IC(tone, excess_20d)=+0.012 (~0, non-predittivo) → conferma FAIL della
  forma debole a sample decision-grade

**Impatto:** anche wired il carburante (BUG-A) e spostato su small-cap (BUG-B),
la **forma** (long-only + polarity + hold 20d) resta debole. POC-2 FAIL (IC≈0)
è la **misurazione diretta** di questo bug: la combinazione specifica non
predice. Per un revival, servirebbe simmetrizzare (short su miss), usare
embedding contestuali, e hold 5-10g. Bug di **design della forma**, non di
logica.

## BUG-D — `pead_signals` table mai materializzata (LOW, persistenza)

**Luogo:** `pead_signals` (DDL solo in ARCHITECTURE.md / doc, nessuna migration).

**Conferma (traccia DB read-only 2026-08-04):**
```
\d pead_signals → "Did not find any relation"
pg_tables WHERE tablename ILIKE '%pead%' → 0 rows
```

**Descrizione:** il commit `d1e6de6` message: "pead_signals never materialized
(DDL was doc-only, no migration) → no drop migration needed." La persistenza
dichiarata (fase 01) non è mai esistita nel DB. I segnali (se generati)
sarebbero stati in Redis (`signal:*:pead_event`, rimosso) MA non nel DB.

**Impatto:** LOW — zero ordini lifecycle → nessuna audit trail DB da
perdere. MA è un'**omissione di persistenza**: se S7 avesse prodotto segnali,
non sarebbero stati persistenti strutturalmente. Per un revival, la migration
deve creare la table. Non un bug di logica, un gap di persistenza.

## OBS-1 — Guard anti-reintroduzione viva (osservazione positiva)

**Luogo:** `tests/test_p0_13_strategy_containment.py:62-97`
(`TestS7NotInOperationalRegistry`).

**Descrizione:** il test **vive nel working tree** e mantiene S7 fuori dal
`StrategyRegistry`. Se S7 viene reintrodotto, deve essere `mode=research` e
**non** in `get_active_strategies()` (non deve ricevere capitale). Questo è
il **bug-prevention** del progetto: impedisce la riesposizione a un alpha
misurato NEGATIVE (POC-2 FAIL decision-grade).

**Conferma (repro_2, ESEGUITO):**
```
test_p0_13_strategy_containment.py exists: True
TestS7NotInOperationalRegistry class present: True
Guard: S7 not in get_active_strategies(): True
Guard: S7 must be mode=research if present: True
=> ANTI-REINTRO GUARD ALIVE: True
CONFIRMED
```

**Impatto:** POSITIVO — questa guard è il **meccanismo di governance corretto**
che manca a S1/S4. Impedisce il "zombie revival" di una strategia killata.
Documentato come **best-practice** per la cross_review (lo stesso pattern
dovrebbe proteggere S1/S4 se vengono ridotti a shadow/rimossi).

---

## Bug non confermati / non ricercati

- **Race conditions**: S7 mai eseguita → nessun path concorrente. N/A.
- **Accounting divergences**: zero trade → nessun P&L. N/A.
- **Look-ahead**: `detected_at` = filing time (event-time corretto nel design),
  backtest mai runnato → look-ahead non testabile. N/A (design OK).
- **Stale-evidence**: `is_active(as_of)` gate su `hold_until` (`pead.py:37-38`)
  corretto nel design; mai eseguito. N/A.
- **Weekend/off-by-one**: `hold_days=20` giorni di calendario (non trading
  days) — `timedelta(days=20)` (`signal.py:55`). **Potenziale bug** (20 giorni
  calendari ≈ 14 trading days, non 20) MA mai eseguito → non confermato.
  Registrato come **UNCONFIRMED**: se S7 fosse stata live, hold 20 calendari
  avrebbe sottesato il drift di ~6 trading days. Non confermato (zero ordini).

## UNCONFIRMED

- **HOLD_CALENDAR vs TRADING**: `hold_until = detected_at + timedelta(days=20)`
  (`signal.py:55`) usa giorni di calendario. Se l'intento era 20 **trading
  days** (PEAD canonico), l'hold reale sarebbe ~14 trading days → drift
  sottocatturato. MA: (1) mai eseguito, (2) la letteratura tone usa 5-10g
  quindi 14 trading days sarebbe in realtà più vicino all'edge vivo di 20. Non
  confermato, impatto ambiguo. Da verificare in un revival.

## Sintesi

S7 ha **zero bug di path live** (mai esistetto). I "bug" sono:

1. **BUG-A (HIGH, operatività)**: carburante zero (consensus mai wired) →
   zero ordini. Gap upstream, non logica S7. (CONFIRMED repro_1)
2. **BUG-B (HIGH, validità)**: universo large-cap competuto vs small-cap vivo.
   Configurazione/design. (CONFIRMED lifecycle + letteratura)
3. **BUG-C (MEDIUM, forma)**: long-only + polarity + hold 20d = combinazione
   debole. Design della forma. (CONFIRMED POC-2 IC≈0 + statica)
4. **BUG-D (LOW, persistenza)**: `pead_signals` table mai materializzata. Gap
   persistenza. (CONFIRMED DB `\d`)
5. **OBS-1 (positivo)**: guard anti-reintro viva. Best-practice governance.
   (CONFIRMED repro_2)

**Critico**: i 4 bug sono **tutti coerenti con la decisione di rimozione**.
Nessun revival parziale (es. solo wired il consensus BUG-A) salverebbe S7,
perché BUG-B (universo) e BUG-C (forma) sono entrambi sulla **forma
debole/competuta** del fenomeno. La rimozione su POC-2 FAIL è la conclusione
corretta. La guard anti-reintro (OBS-1) proteggerà contro un revival
non-giustificato.

**Confronto con S4**: S4 ha bug nel **backtest** (gate drift, fallback
sintetico) MA il path live è corretto (esegue fedelmente un segnale IC<0). S7
non ha path live (mai eseguita) MA i bug sono nella **configurazione del
segnale** (carburante, universo, forma). S7 è stata killata prima di esporre
il sistema; S4 esegue live con IC<0. La **governance di S7 è superiore**.

---
**Stato fase:** 07_bugs = **done**. Prossimo cursore: `S7:08_report`.