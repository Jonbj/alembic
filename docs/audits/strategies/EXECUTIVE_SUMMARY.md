# EXECUTIVE_SUMMARY — Audit strategie Alembic

**Audit:** Alembic Strategy Audit (skill `/alembic-strategy-audit`)
**Data:** 2026-08-04
**Scope:** S1, S2, S3, S4, S7 — 5 strategie auditate, fasi 01-08 per ciascuna
+ cross-review.
**Metodo:** read-only, resumable, cron 30m; codice + DB read-only + git
history + letteratura accademica + repro eseguiti.

## Sintesi esecutiva

L'audit ha esaminato **ogni** strategia del progetto (non solo quelle
attive): S1 (TimeSeriesMomentum), S2 (VRPStrategy), S3
(CrossSectionalMomentum/residual momentum), S4 (NewsDrivenTactical), S7
(PEAD, rimossa). Il quadro che emerge è **duplice**:

1. **Nessuna strategia genera alpha genuino netto misurabile**. I verdetti
   vanno da `NEGATIVE` (S2, S4, S7) a `DECAYED` (S1, S2, S4, S7) a `UNPROVEN`
   (S3, implementazione non fedele MA fenomeno NON decaduto). **Non c'è una
   strategia `GENUINE_NET_ALPHA`.**

2. **Il progetto sa come killare correttamente una strategia (S7) ma non lo
   applica alle strategie live (S1, S4)**. S7 è il caso di best-practice
   governance: POC pre-registrato, misurazione decision-grade, kill criterion
   applicato, rimozione pulita, guard anti-reintro. S1/S4 sono live nonostante
   IC<0/decay senza kill criterion. **La governance asimmetrica è il rischio
   sistemico principale.**

## Verdetti classificati (per confidenza + severità)

| Rango | Strategia | Impl. | Fenomeno | Live? | Confidenza | Note critiche |
|---|---|---|---|---|---|---|
| 1 | **S7** PEAD | **NEGATIVE** | DECAYED | no (rimossa) | **ALTA** | Best-practice governance; POC-2 FAIL decision-grade cross-model; carburante zero (consensus mai wired) |
| 2 | **S4** NewsDriven | **NEGATIVE** (IC) | DECAYED | **sì (paper, esegue)** | MEDIA | IC<0 (s4_ic.json), P0-13 non confermato; P&L +$329 = beta+noise; bug solo backtest; nessun bug path live |
| 3 | **S2** VRP | **NEGATIVE** | DECAYED | no (dead config) | MEDIA | Implementazione = long-SPY non-VRP; look-ahead fwd_21d CRITICAL; dead config; IV stale |
| 4 | **S1** TSMOM | **DECAYED** | DECAYED | **sì (paper)** | MEDIA-BASSA | Dead config; look-ahead pannello; gate banale Sharpe≥0; momentum large-cap decaduto post-2018; niente IC decision-grade |
| 5 | **S3** CrossSec | **UNPROVEN** (non fedele) | UNPROVEN (NON decaduto) | no (morto) | MEDIA | Implementazione diverge da design #55 (12-0 vs 12-1, long-only vs LS); fenomeno residual momentum NON decaduto (Huij-Lansdorp 2017) → candidato revival |

**Ordine di priorità d'azione**: S4 (live con IC<0, il rischio attivo) →
S1 (live senza misurazione) → S3 (opportunità, fenomeno vivo) → S2/S7
(morti, pulizia).

## I 3 rischi principali

### R1 — Eseguire su alpha misurato negativo (S4) e non misurato (S1) [ALTO]

S4 è live in paper con IC<0 (il progetto stesso lo misura in `s4_ic.json`:
−0.018/−0.010/−0.026, peggiore di placebo). `promotion_blocked=true` trattiene
dal `mode=live` MA l'esposizione in paper è comunque un costo: attenzione
dell'operatore, churn, e rischio di promozione futura su backtest
non-rappresentativo (BUG-A gate drift + BUG-B fallback sintetico). S1 è live
senza IC misurato a decision-grade.

**L'evidenza S7 dimostra che il progetto sa che la risposta è killare** — ma
non lo applica a S1/S4. L'asimmetria di governance (GI-5) è il rischio
sistemico: promuovere/mantenere strategie su base non-evidence.

**Azione**: applicare PO-5 (modello S7) a S1/S4. Misurare IC a decision-grade
(n≥73, cross-model), pre-registrare kill criterion ("Se IC≤0 → ridurre a
shadow o rimuovere"), applicarlo. Per S4: estendere s4_ic.json a 73gg+ (34gg
è small-sample ma la direzione è coerente).

### R2 — Reversal S1↔S4 senza conciliazione [ALTO]

S1 e S4 operano sugli stessi ticker e possono generare segnali opposti. La
memory `project_loss_analysis_2026_07_16` documenta il **loop reversal
S1↔S4** come causa della perdita −$83.86 (2026-07-16). La trace DB mostra 25
exit `sentiment_reversal` (S4 che exita, potenzialmente, posizioni S1
proficue). **Non c'è un layer di conciliazione** che decida chi vince quando
S1 e S4 confliggono su un ticker.

**Azione**: introdurre un layer di conciliazione esplicito (priorità core S1,
voto ponderato, o veto incrociato). Documentare la gerarchia di exit. Il loop
reversal va rotto strutturalmente, non tarando le soglie.

### R3 — Backtest non-rappresentativi come decision gate [MEDIO-ALTO]

I backtest S1/S2/S3/S4 sono invalidati da look-ahead (S1/S2/S3 pannello
bilanciato / fwd_21d), survivorship (S3), gate drift (S4), o fallback
sintetico (S4). Qualunque decisione di promozione basata su questi backtest
è a rischio. S1 è live basandosi su backtest invalidati. S4 ha
`promotion_blocked` (quindi non decide sul backtest) MA se il blocco viene
rimosso, il backtest non-rappresentativo potrebbe illudere di validazione.

**Azione**: validare i backtest con un audit look-ahead/survivorship formale
(PIT-strict) prima di decidere. Adottare il modello S7 per le decisioni
future: **POC IC pre-registrato a decision-grade come gate**, non backtest WF.
Il backtest come gate è inaffidabile per la maggior parte delle strategie.

## I 3 difetti trasversali

### D1 — Forma debole trasversale (GI-4)

**Tutte** le strategie implementano la **gamba debole** del rispettivo
fenomeno: long-only (non simmetrico), polarity sentiment (non embedding,
decade OOS), large-cap (non small-cap dove l'edge vivo), orizzonte mismatch.
Non è un caso isolato — è un **pattern di design**. La combinazione
"long-only + polarity + large-cap + orizzonte sbagliato" è il deficit di
design alpha più importante: nessuna strategia è configurata sulla forma viva.

**Azione**: il prossimo research alpha deve **invertire ogni dimensione**:
short leg, embedding contestuale, small/mid-cap, orizzonte al picco dell'edge.
Le strategie attuali sono la forma debole da cui allontanarsi, non la base
su cui costruire.

### D2 — Dead config `from_yaml` (GI-1)

S1/S2/S3 definiscono `XxxConfig.from_yaml` MA con **0 call site** → la
config yaml è documentazione morta. L'operatore crede di poter tarare via
yaml MA i default hard-coded governano. S4 è l'eccezione (wired via
`trading.yaml`). Questo è il deficit di **controllabilità** più grave.

**Azione**: wired `from_yaml` al runtime, o rimuoverli e documentare "config
morta, modificare i default in `src/strategies/<id>/strategy.py`".

### D3 — Soglie gate banali + IC non misurato a decision-grade (GI-3, GI-8)

S1/S3 ammettono Sharpe=0.0 (no-op) come PASS. S4 ha IC misurato MA n=34
(small-sample). S1 non ha IC cross-sectionale. Solo S7 ha misurato IC a
decision-grade (n=73). Senza misurazione decision-grade, non c'è base per
killare/promuovere → sottende la governance asimmetrica (R1).

**Azione**: threshold pre-registrati >0 per tutti i gate. Misurare IC (o
metrica equivalente time-series) a decision-grade per S1/S4.

## Opportunità: S3 residual momentum (fenomeno NON decaduto)

S3 è l'**eccezione positiva** dell'audit: il **fenomeno** (residual momentum,
Blitz-Huij-Martens 2011) è **NON decaduto** (Huij-Lansdorp 2017 OOS, ~2x
Sharpe di total momentum, alpha incrementale). L'**implementazione** è
UNPROVEN (non fedele: 12-0 vs 12-1, long-only vs long-short, sizing non
normalizzato, pannello bilanciato look-ahead, survivorship) MA il fenomeno
sopravvive. S3 è **il candidato più promettente per il prossimo research
alpha** — MA richiede implementazione fedele:
- orizzonte 12-1 (non 12-0, evitare contaminazione reversal),
- long-short simmetrico (non long-only),
- vol-normalizzazione cross-sectionale,
- small/mid-cap (con copertura dati),
- pannello PIT-strict (no look-ahead),
- POC IC pre-registrato a decision-grade prima di promuovere.

**Azione**: S3 come base per la prossima strategia, implementata fedelmente
alla letteratura, con governance PO-5 (modello S7).

## Limiti dell'audit

- **S1 IC**: non misurato a decision-grade (time-series, no cross-sectional
  IC). Verdetto DECAYED su letteratura + pattern, non misurazione diretta.
- **S4 IC**: n=34 (small-sample), direzione coerente negativa MA n<73.
- **S3**: runtime morto → nessuna evidenza runtime; UNPROVEN su
  implementazione non-fedele.
- **S7 resurgence post-2020**: ambigua (Nyllinge 2025, n=4 anni), non
  robusta. Non cambia il verdetto S7 MA caveat per revival.
- **Costi live**: non misurati direttamente; inferiti da `cost_bps`/`cost_usd`
  + letteratura.
- **Freeze taratura** (memory `project_osservazione_backtest_2026_08_01`,
  issue #171): 03/08→28/09, 40gg borsa. Le raccomandazioni di taratura sono
  **post-freeze**. Nessuna azione di taratura durante il freeze.

L'evidenza è **sufficiente per i verdetti** con la confidenza dichiarata per
strategia (S7 ALTA, S4/S2/S3 MEDIA, S1 MEDIA-BASSA per limiti di misurazione).

## Messaggio finale

Il progetto ha **pipeline offline feature-complete** (CLAUDE.md) e
**infrastruttura di controllo robusta** (lifecycle, promotion_blocked,
provenance, guard anti-reintro, POC pre-registrati) — MA **non ha alpha**
misurabile in nessuna strategia live, e **non applica uniformemente** la
governance che sa esercitare (S7). La priorità non è "fixare S1/S4" ma:

1. **Estendere la governance di S7 a tutto il sistema** (R1): misurare,
   pre-registrare kill criterion, applicare. Due strategie live che si
   inversionano (R2) è peggio di una core sola.
2. **Costruire la prossima strategia sulla forma viva del fenomeno** (D1,
   S3): short, embedding, small-cap, orizzonte ottimale, implementazione
   fedele, POC decision-grade.
3. **Validare i backtest prima di decidere** (R3): adottare POC IC come gate.

Il progetto ha **tutto ciò che serve per farlo** — l'infrastruttura, il
processo (S7 lo dimostra), e un fenomeno non-decaduto (S3 residual momentum).
Manca solo **l'applicazione uniforme della governance** e il **coraggio di
ridurre a shadow/rimuovere** ciò che è misurato negativo.

---

**Documenti audit (tutti in `docs/audits/strategies/`):**
- `STATE.md` (cursore resume), `strategies.json`, `DISCOVERY.md`
- `S1/REPORT_S1.md` … `S7/REPORT_S7.md` (+ fasi 01-07, STATUS.json, repro)
- `GLOBAL_ISSUES.md` (10 difetti trasversali)
- `EVIDENCE.md` (query DB, repro, ref letteratura)
- `PORTFOLIO_INTERACTIONS.md` (7 interazioni)
- `EXECUTIVE_SUMMARY.md` (questo documento)
- `COMPLETE` (sentinel — creato a fine audit)

---
**Stato:** EXECUTIVE_SUMMARY = done (4/4 cross_review). Prossimo: `COMPLETE` sentinel.