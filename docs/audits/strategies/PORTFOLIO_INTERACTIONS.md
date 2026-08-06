# PORTFOLIO_INTERACTIONS — Interazioni a livello portfolio

**Audit:** Alembic Strategy Audit
**Data:** 2026-08-04
**Scope:** S1, S2, S3, S4, S7 — come interagiscono/confliggono nel book

Questo documento analizza come le strategie **interagiscono a livello
portfolio**: sleeve caps, cross-strategy reversals, shared risk overlays,
signal_id coupling, momentum beta duplication. Le strategie non operano in
isolamento — si condividono il book, il capitale, e gli overlay di rischio.

## Mappa dello stato live (2026-08-04)

| Strategia | Live? | Sleeve | Allocazione | Ruolo nel book |
|---|---|---|---|---|
| S1 TimeSeriesMomentum | **sì (paper)** | principale | ~98% del peso (esecuzione_decisions S1) | core momentum |
| S4 NewsDrivenTactical | **sì (paper)** | overlay 10% | bucket_pct 0.10 × 1/5 fixed-slot = 2% per ticker | sentiment overlay |
| S2 VRP | no (dead config) | — | — | morto |
| S3 CrossSectional | no (morto) | — | — | mai deployato |
| S7 PEAD | no (rimossa) | — | — | mai live |

**Book live = S1 (core) + S4 (overlay 10%)**. S2/S3/S7 non contribuiscono.

## PI-1 — Cross-strategy reversal S1↔S4 (HIGH, conflitto)

**Meccanismo:** S1 (time-series momentum) e S4 (news sentiment) operano sugli
**stessi ticker** dell'universo large/mid-cap US. Possono generare segnali
**opposti** sullo stesso ticker nello stesso periodo:
- S1 momentum SELL (rendimento recente negativo → trend down),
- S4 sentiment BUY (news positive → drift positivo),

o viceversa. La memory `project_loss_analysis_2026_07_16` documenta il **loop
reversal S1↔S4** come causa della perdita −$83.86 (2026-07-16): S1 e S4 si
inversionavano a vicenda, generando churn e trade losses.

**Conferma (trace DB):** `trades.exit_reason = sentiment_reversal` (25 trade)
→ S4 sentiment reversal triggera exit di posizioni (potenzialmente S1). La
colonna `exit_reason` mostra `sentiment_reversal` come terza causa di exit
(dopo `portfolio_sell` 304 e `stop_loss` 33).

**Layer di conciliazione?** Il `portfolio_scheduler` aggrega i target weights
per strategia MA **non c'è un layer esplicito di conciliazione** che decida
quale strategia "vince" su un ticker quando i segnali confliggono. L'exit
S4 (`sentiment_reversal`) può chiudere una posizione S1 senza che S1 abbia
generato un signal di exit. → **S4 può sovrascrivere S1** sullo stesso ticker.

**Impatto:** il reversal S1↔S4 è la **causa documentata di perdita** più
chiara del sistema (−$83.86, 2026-07-16). Senza conciliazione, due strategie
con segnali opposti si annullano a vicenda → churn + costi + loss.

**Raccomandazione:** introdurre un **layer di conciliazione esplicito**:
quando S1 e S4 generano segnali opposti su un ticker, decidere con una regola
(es. priorità alla strategia core S1, o voto ponderato, o veto incrociato).
Documentare chi "possiede" il ticker. Il loop reversal deve essere rotto
strutturalmente, non tarando le soglie.

## PI-2 — Momentum beta duplication S1 + S4 (MEDIUM, esposizione)

**Meccanismo:** S1 (time-series momentum) e S4 (news sentiment) sono
**entrambi long-only positivi** su large-cap. C'è un **overlap di beta**:
- S1 long momentum → long i titoli che hanno reso positivo recente,
- S4 long sentiment → long i titoli con news positive,

MA **news positive correlate con rendimento positivo recente** (le aziende
che performano bene hanno news positive). Quindi S4 long sentiment ≈ S1 long
momentum su molti ticker → **duplicazione di momentum beta**.

**Conferma (logica + letteratura):** Heston-Sinha (REPORT_S4 fase 03): news
positive incorporate rapidamente → sentiment+ ≈ prezzo già salito ≈ momentum+.
Il bucket S4 top-5 sentiment+ è sovrapponibile al bucket S1 momentum+ su
large-cap liquide.

**Misurazione nel progetto:** non c'è una misurazione esplicita dell'overlap
S1∩S4 (es. Jaccard similarity dei ticker target per ciclo). Da misurare.

**Impatto:** S4 come "overlay di conferma a S1" (REPORT_S4 fase 02) **non è
incrementale** se duplica momentum beta. L'IC di S4 (negativo, fase 04)
misura il contenuto informativo **incrementale** → IC<0 suggerisce che S4 non
aggiunge info oltre S1 (e beta di mercato). S4 sta **duplicando** esposizione,
non confermando.

**Raccomandazione:** misurare l'overlap S1∩S4 (Jaccard dei target weights per
ciclo). Se elevato (>50%), S4 non è incrementale → ridurre a shadow o
rimuovere. L'IC<0 è coerente con "S4 non aggiunge info oltre S1".

## PI-3 — Sleeve caps e allocazione del capitale (MEDIUM, struttura)

**Meccanismo:** il book ha **due sleeve**:
- S1: sleeve principale (quasi tutto il book, ~98% del peso esecuzioni),
- S4: sleeve overlay `bucket_pct=0.10` (10% del book), cap hard 10%
  (`registry.py:228`), fixed-slot 1/5 = 2% per ticker.

**Cap interaction:** S4 cap 10% limita l'overlay MA non c'è un **cap esplicito
S1** documentato in audit (S1 prende il residuo). Con `regime_mult=0.700`
(S4 trace DB) il deployment è limitato a 70% del target → **capital
deployment limitato dal regime_mult ×0.2** (chiavi regime/VIX assenti, memory
`project_capital_deployment_regime`) → non dal cap S4 10%.

**Impatto:** il sistema è **underdeployed** (memory
`project_asis_underdeployment_loop`: theoretical max 22.4%, observed 26.2%) a
causa di conservativismi non calibrati (regime_mult, floor, caps). S1+S4 non
usano pienamente il capitale disponibile. Questo **non è un bug** (è
conservativo) MA limita la rilevabilità dell'alpha (piccole posizioni →
P&L dominato da noise/costi).

**Raccomandazione:** l'underdeployment è un **loop di conservativismi** non
una leva sola (memory `project_asis_underdeployment_loop`). La taratura è
**congelata 03/08→28/09** (memory `project_osservazione_backtest_2026_08_01`,
issue #171) → non toccare ora. Ma post-freeze, calibrare i conservativismi
misurando l'impatto di ciascuno.

## PI-4 — Shared risk overlays (stop, drawdown, kill-switch) (MEDIUM, rischio)

**Meccanismo:** S1 e S4 condividono **risk overlays**:
- **Stop-loss** (`stop_policy.py`): applicato a entrambe (S4 non ha stop S4
  specifico, REPORT_S4 fase 06 asse 8 "no stop S4" → usa lo stop globale),
- **Drawdown / kill-switch** (`feedback:regime_scale`, `peak_equity`): la
  memory `project_bug_sweep_2026_07_22` documenta il **kill-switch drawdown
  disabilitato (peak_equity mai inizializzato)** — HIGH bug non fixato in
  audit (fuori scope strategie, è infrastruttura),
- **regime_mult**: condiviso, ×0.700 su S4 (trace DB), limita entrambe.

**Conferma (trace DB):** `trades.stop_strategy`, `stop_mode`, `stop_k`,
`stop_vol_at_entry` popolati → stop attivo su entrambe. `regime_mult` in
`execution_decisions` = 0.700.

**Impatto:** gli overlay condivisi sono **corretti** (un book unificato usa
un risk layer) MA:
- **S4 senza stop S4-specifico** → dipende dallo stop globale (disegnato per
  S1 momentum). Lo stop 2% (memory `project_stop_loss_evidence_2026_07_10`:
  0.26-0.53σ → stop-out su rumore) è tarato per S1, non per S4 tattico.
- **Kill-switch drawdown disabilitato** (bug sweep 2026-07-22, non fixato) →
  il drawdown protection non funziona per nessuna strategia. È un rischio
  **infrastrutturale trasversale** (non strategia-specifico).

**Raccomandazione:** lo stop di S4 andrebbe tarato per il profilo tattico
giornaliero (non il 2% momentum). Il kill-switch drawdown (bug sweep) va
fixato a livello infrastruttura (fuori scope audit strategie, MA è il rischio
sistemico più grave).

## PI-5 — Signal_id coupling S1↔S4↔trades (LOW, provenance)

**Meccanismo:** `trades` non ha `strategy_id` (fase 06, S7). L'attribuzione
del trade a una strategia è via `signal_id` (join con `execution_decisions`
che ha `reason` taggato S1/S4). La memory `project_functional_audit_2026_07_22`
documenta il **desync signal_id↔score (#59 vivo)** — un bug di provenance.

**Conferma (memory + trace):** `trades.signal_id` ↔ `execution_decisions`
join funziona MA il desync #59 (vivo) può far attribuire un trade alla
strategia sbagliata. S4 ha il fix provenance pinning (B33/#109, REPORT_S4
fase 07 "no bug path live") MA il desync #59 è più ampio.

**Impatto:** l'attribuzione P&L per strategia può essere imprecisa se il
desync #59 non è fully risolto. Per la forensic e la misurazione (IC per
strategia), questo è un rischio. LOW perché il fix B33 ha mitigato il caso
peggiore (provenance pinning).

**Raccomandazione:** chiudere il desync #59 (memory
`project_functional_audit_2026_07_22`). L'attribuzione per-strategia è
prerequisito per misurare IC/Sharpe per strategia a decision-grade.

## PI-6 — Exit reason sovrapposti (MEDIUM, logica di exit)

**Meccanismo:** `trades.exit_reason` mostra 5 categorie:
- `portfolio_sell` (304) — rebalance (peso target → 0),
- blank (49) — non attribuito,
- `stop_loss` (33) — stop globale,
- `sentiment_reversal` (25) — **S4 triggera exit** (potenzialmente di posizioni S1, PI-1),
- `LEGACY_FLATTEN` (16) — legacy flatten (memory
  `project_loss_analysis_2026_07_16`: loop reversal fixato #67/#68).

**Conflitto:** `sentiment_reversal` (S4) e `portfolio_sell` (rebalance) sono
**cause di exit sovrappesti**. Un ticker può essere exitato da S4
sentiment_reversal mentre S1 vorrebbe mantenerlo (momentum ancora up). Non
c'è una **gerarchia di exit** documentata (chi vince tra S4 reversal e S1
hold?).

**Impatto:** le 25 exit `sentiment_reversal` sono potenzialmente **exit
premature di posizioni S1 proficue**. Se S4 sentiment flipa a negativo MA S1
momentum è ancora up, S4 exita una posizione che S1 manterrebbe → perdita
del drift momentum.

**Raccomandazione:** documentare la gerarchia di exit (S1 core tiene vs S4
overlay exita?). Se S4 è overlay di conferma, l'exit S4 non dovrebbe
sovrascrivere S1 core — solo veto entry (non forzare exit). Il loop reversal
(PI-1) è la manifestazione di questa mancanza di gerarchia.

## PI-7 — Strategie morte che non contribuiscono (LOW, osservazione)

S2 (dead config), S3 (mai deployato), S7 (rimossa) **non contribuiscono** al
book. MA:
- **S2** è ancora in `config/strategies.yaml`? (dead config GI-1) —
  l'operatore può credere sia attiva.
- **S3** fenomeno NON decaduto (REPORT_S3 fase 04) → candidato al revival MA
  richiede implementazione fedele (12-1, long-short, normalizzato, small-cap).
- **S7** guard anti-reintro (OBS-1) protegge.

**Raccomandazione:** S3 è il candidato **più promettente** per il prossimo
research alpha (fenomeno NON decaduto, Huij-Lansdorp 2017) MA richiede
implementazione corretta. S2 (VRP) e S7 (PEAD large-cap) sono decaduti —
non revivalare. Pulire `strategies.yaml` dalle entry morte (GI-1).

## Sintesi interazioni

| Interazione | Strategie | Severità | Stato |
|---|---|---|---|
| PI-1 reversal S1↔S4 | S1, S4 | HIGH | documentato (−$83.86), no conciliazione |
| PI-2 momentum beta duplication | S1, S4 | MEDIUM | non misurato (Jaccard), IC<0 coerente |
| PI-3 sleeve caps / underdeployment | S1, S4 | MEDIUM | congelato 03/08→28/09 (#171) |
| PI-4 shared risk overlays | S1, S4 | MEDIUM | stop S4 non tarato, kill-switch bug |
| PI-5 signal_id coupling | S1, S4 | LOW | desync #59 vivo (B33 mitigato) |
| PI-6 exit reason sovrapposti | S1, S4 | MEDIUM | no gerarchia exit documentata |
| PI-7 strategie morte | S2, S3, S7 | LOW | S3 candidato revival (NON decaduto) |

**Il book live (S1+S4) ha due problemi strutturali**: (1) **reversal senza
conciliazione** (PI-1, causa di perdita documentata), (2) **duplicazione di
momentum beta** (PI-2, S4 non incrementale). Entrambi puntano alla stessa
conclusione: **S4 come overlay di S1 non sta funzionando** — o si annulla
(reversal) o duplica (beta). L'IC<0 di S4 (fase 04) è la misurazione diretta
di "S4 non aggiunge info incrementale."

**Raccomandazione centrale**: il sistema dovrebbe **semplificare** — ridurre
S4 a shadow (non eseguire, solo misurare IC), mantenere S1 come core, e
investire il prossimo research alpha in **S3 residual momentum (fenomeno NON
decaduto) implementato fedelmente** o in una nuova strategia sulla **forma
viva** del fenomeno (GI-4: short, embedding, small-cap). Due strategie live
che si inversionano è peggio di una sola core.

---

## Correzioni post-audit (2026-08-06, verifica sul codice e su GitHub)

Due affermazioni di questo documento riprendono memory non più attuali.

### PI-4 — il kill-switch drawdown **è** fixato

Il testo lo riporta come *"HIGH bug non fixato"* citando il bug sweep del
2026-07-22. Verificato: `_peak_and_drawdown` (`portfolio_scheduler.py:368-380`)
seeda `peak = equity` alla prima osservazione, e la docstring cita
esplicitamente il bug del 2026-07-22 come risolto. Su Redis live
`portfolio:peak_equity` è valorizzato.

Quindi il "rischio infrastrutturale trasversale più grave" indicato in PI-4
non esiste più. La memory da cui derivava era anteriore al fix.

### PI-5 — la issue #59 è chiusa

Il testo cita *"il desync signal_id↔score (#59 vivo)"*. `gh issue view 59` →
**CLOSED** (*"S4: pin exact signal_id/score/reasoning at decision time"*).
Resta aperta #123, che riguarda un sintomo correlato ma distinto
(`trades.signal_score` senza `signal_id` corrispondente). La chiusura di #59
non dimostra da sola che il desync sia sparito, ma la issue non è "viva".

### PI-1 / PI-6 — confermate e quantificate

Le due interazioni descritte qui si sono verificate di nuovo il 2026-08-05, con
il meccanismo ora identificato: lo scheduler ridecide l'intero book ogni 15
minuti ignorando la frequenza di ribilanciamento dichiarata, e S1 non ha banda
morta attorno a z=0. BP ha fatto due round trip completi in quattro ore
(1,2% → 0% → 1,2% → 0%), −$18.50 e $3.94 di costi. Dettaglio in #185; la
gerarchia di uscita mancante è #182.

---
**Stato:** PORTFOLIO_INTERACTIONS = done (3/4 cross_review). Prossimo: `EXECUTIVE_SUMMARY.md`.