# S2 — 07 Bug confermati

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Metodo di conferma:** ogni bug è confermato con (a) uno script di riproduzione
eseguibile sotto `S2/`, (b) una traccia statica deterministica, o (c) un
controesempio matematico. Nessun bug è asserito senza evidenza.

## Legenda severità
`CRITICAL` = perdita di denaro / bias che invalida l'evidenza · `HIGH` =
governance/sicurezza · `MED` = qualità/mantenibilità · `LOW` = minore.

**Contesto:** S2 è `enabled=false` con hard-block nel registry (`registry.py:231`)
e `mode=disabled`/`approved=false` nel lifecycle DB. Nessun bug ha impatto runtime
su capitale reale (S2 è morto in produzione, confermato da DB: zero `stop_strategy='S2'`
nei trades ultimi 30g). I bug sono difetti del codice di backtest/design, non rischi
live attivi.

---

## BUG-A — Look-ahead nella classificazione bull/bear del regime gate (gate 4)
- **Severità:** CRITICAL (invalida il gate 4 del backtest)
- **Sintomo:** `_split_regime_returns` (`backtest.py:202-211`) etichetta ogni data OOS
  `t` come `bull`/`bear` usando `fwd_21d = cum_return.shift(-21)/cum_return - 1`,
  ovvero il rendimento cumulato **da t a t+21** (dati futuri). Il commento del codice
  stesso ammette "Forward-looking". Il gate_4 (regime) di `summary.json` è valutato
  su queste etichette → hindsight intra-OOS.
- **Conferma:** `S2/repro_1_regime_lookahead.py` (eseguito 2026-08-04) —
  controesempio deterministico: alla data giorno 20, con rendimenti giorni 0..20
  identici, il caso A (rendimenti futuri +1%/g) → label `bull`, il caso B
  (rendimenti futuri −1%/g) → label `bear`. L'etichetta di giorno 20 dipende
  esclusivamente dai rendimenti giorni 21..41.
- **Loco:** `src/strategies/s2/backtest.py:202-211`.
- **Impatto:** il gate 4 (regime Sharpe per bull/bear/high_vol/low_vol) non è
  valido: la classificazione bull/bear non è conoscibile al tempo `t`. Stessa
  famiglia di bias di S1 OBS-4 (regime circolare), ma qui **attivo** nel gate di
  validazione (non solo osservazione).

## BUG-B — `apply_regime_scale` è dead code (mai chiamato)
- **Severità:** MED (dead code; il regime modulation sul put non avviene)
- **Sintomo:** `regime.py:44-62` definisce `apply_regime_scale(signal, modulation)`
  per scalare il `quantity` del put di `floor(qty·scale)` e aggiornare il
  collaterale — la "regime modulation" documentata. La funzione è importata in
  `strategy.py:43` ma **nessun call site** esiste in tutto `src/`.
- **Conferma:** `S2/repro_2_deadconfig.py` (eseguito 2026-08-04) — `ast.walk` su
  `src/**/*.py`: 0 invocazioni della funzione `apply_regime_scale` di regime.py
  (le occorrenze "apply_regime_scale" in `portfolio_scheduler.py`/`performance.py`
  sono la **chiave di config F8** `loss_feedback.apply_regime_scale`, un oggetto
  diverso). Il regime scale nel path backtest è applicato solo via
  `_target_spy_shares` al notionale equity, non sul `quantity` put.
- **Loco:** `src/strategies/s2/regime.py:44-62`; import morto `strategy.py:43`.
- **Impatto:** divergenza tra spec del modulo regime (scalare il put) e
  implementazione (scalare l'equity). Coerente con DV-3/DV-4 (la put è
  decorativa) ma indica codice morto e documentazione fuorviante.

## BUG-C — Reprice put e SIGNAL_FLIP usano l'IV di entry (stale), non IV corrente
- **Severità:** HIGH (logica di exit; distorce SIGNAL_FLIP)
- **Sintomo:** `_reprice_put` (`strategy.py:158-174`) prezza la put con
  `sigma=signal.implied_vol` (IV di **entry**), non l'IV corrente alla data `ts`.
  `evaluate_exit` riceve `implied_vol=pos.signal.implied_vol` (entry IV,
  `strategy.py:220`) → SIGNAL_FLIP confronta `IV(entry) − RV(corrente) < 0`, non
  `IV(corrente) − RV(corrente)`.
- **Conferma:** traccia statica:
  - `strategy.py:171` `sigma=signal.implied_vol` (reprice, IV entry);
  - `strategy.py:220` `implied_vol=pos.signal.implied_vol` (passato a evaluate_exit);
  - `exit.py:101-103` `if implied_vol - realized_vol < 0: return SIGNAL_FLIP`.
  - ⇒ il flip si triggera quando RV supera l'IV **di entry**, ignorando i
    movimenti della superficie IV dopo l'entry. Una put il cui IV di mercato
    raddoppia (vol spike) ma con RV ancora sotto l'IV entry non triggera flip.
- **Loco:** `src/strategies/s2/strategy.py:171,220`; `src/strategies/s2/exit.py:101-103`.
- **Impatto:** le uscite SIGNAL_FLIP (e indirettamente TARGET_PROFIT/STOP_LOSS via
  `current_mid`) sono distorte da IV stale; il backtest sottovaluta l'effetto di
  spike di volatilità post-entry.

## BUG-D — Dead config: nessun loader yaml, nessun file `config/s2*.yaml`
- **Severità:** HIGH (governance — latente; come S1 BUG-1 ma più esplicito)
- **Sintomo:** a differenza di S1/S3 che definiscono `S2Config.from_yaml`, S2 non
  ha metodo `from_yaml`, non esiste file `config/s2*.yaml`, e ogni call site usa
  `S2Config()` defaults. L'unico modo per tarare S2 è editare la dataclass
  `src/strategies/s2/config.py`. Un operatore che cercasse di "cambiare il config
  S2" via yaml non avrebbe alcun effetto (non c'è né il file né il loader).
- **Conferma:** `S2/repro_2_deadconfig.py` (eseguito 2026-08-04) —
  `S2Config.from_yaml` assente (`ast.walk` su config.py: 0 `from_yaml`);
  `config/s2*.yaml` inesistente (`glob` → NONE); call site di `S2Config()` = 2
  (strategy.py, backtest.py), `S2Config.from_yaml()` = 0.
- **Loco:** `src/strategies/s2/config.py` (solo defaults); `backtest.py:57`
  `s2_config = s2_config or S2Config()`; `portfolio_scheduler.py:3074`
  `return VRPStrategy(prices=bars_df)`.
- **Impatto:** governance: nessuna taratura esterna possibile; i default sono
  hardcoded. Coerente con S1 BUG-1 (pattern dead-config) ma più grave perché non
  esiste nemmeno il file yaml o il loader. Inerte in produzione perché S2 è
  disabled, ma blocca eventuali esperimenti futuri via config.

## BUG-E — Accounting divergence: il P&L short-put non entra nel NAV
- **Severità:** CRITICAL (invalida l'evidenza di backtest — il numero misurato non
  è la strategia descritta)
- **Sintomo:** `compute_pnl` (`exit.py:39-45`) calcola il P&L short-put
  `(entry_mid − current_mid)·qty·100` e lo restituisce in `ExitSignal.pnl`. Il
  caller `__call__` (`strategy.py:226-242`) usa solo `exit_signal.reason` per il
  log (`log.debug("S2 EXIT at %s: %s mid=%.2f", ts_date, exit_signal.reason,
  current_mid)`) ed emette un ordine SELL SPY. **`exit_signal.pnl` non è mai
  scritto nel portafoglio.** Il NAV (`portfolio.py:97` = `cash +
  total_position_value`, solo equity) riflette solo il P&L long-SPY.
- **Conferma:** `S2/repro_3_accounting.py` (eseguito 2026-08-04) — due scenari di
  uscita identici tranne per il mark della put: scenario X (put collassata, mid
  0.10, P&L put +$1900) vs scenario Y (put esplosa, mid 5.00, P&L put −$3000).
  Differenza di P&L put = $4900. NAV misurato dal backtest S2: **identico**
  ($119,800 in entrambi; differenza $0). Il P&L put ($4900 di differenza) è
  invisibile al NAV.
- **Loco:** `src/strategies/s2/strategy.py:226-242` (pnl scartato);
  `src/strategies/s2/exit.py:39-45,76` (pnl calcolato);
  `src/backtest/engine/portfolio.py:97` (NAV = cash + equity).
- **Impatto:** l'OOS Sharpe −0.613 di `summary.json` misura una posizione
  **long-SPY mensile gate-da-regime**, non il P&L short-put VRP. L'evidenza
  numerica interna non è interpretabile come test del VRP. Combinato con DV-5
  (sostituzione vietata dal PO), questo è il heart della non-validità di S2 come
  strategia VRP.

---

## Osservazioni NON confermate come bug (registrate per trasparenza)

- **OBS-1 — Filtro VRP quasi tautologico su catena sintetica** (`signal.py:100-101`):
  `select_put` opera su una catena sintetica dove IV è derivata dallo stesso
  underlying della RV63; il filtro `IV−RV≥0` su IV simulata ≈ RV può essere
  soddisfatto quasi sempre per costruzione. `UNCONFIRMED` come bug (dipende
  dall'implementazione di `OptionChainDataLoader.generate_chain`, fuori scope S2).
- **OBS-2 — Gate 5 stress trivialmente PASS** (`summary.json`): worst_drawdown
  cum_return +0.0028 DD −0.0001, vix_2018 cum_return 0.0 — la posizione era quasi
  nulla in quei periodi. Non un "bug" di codice ma un gate non informativo;
  registrato in fase 06 asse 5.
- **OBS-3 — `capital=100_000.0` hardcoded in select_put** (`strategy.py:267`): il
  sizing opzioni usa un capitale fisso 100k, non il NAV reale del backtest. Ma il
  sizing SPY-equivalent (`_target_spy_shares`) usa il NAV reale → `signal.quantity`
  è disaccoppiato dal sizing effettivo. Coerente con BUG-B (put decorativa).
  `UNCONFIRMED` come bug standalone; è conseguenza di DV-4.
- **OBS-4 — `_run_perturbation` non popola gate 3** (`backtest.py:96,157-184`):
  `summary.json` gate_3 = "no perturbed sharpe data provided" nonostante
  `run_robustness=True`. La condizione `len(oos_returns) > 20` dovrebbe passare con
  3 finestre OOS da 252g, ma il gate riceve `perturbed_sharpes=None`. Da
  verificare se `_run_perturbation` ritorna lista vuota (tutte le perturbazioni
  falliscono `health_check` o sollevano eccezioni) — `UNCONFIRMED`; necessita
  esecuzione del backtest (fuero scope: non eseguo backtest in audit read-only).

## Sintesi

| ID | Bug | Severità | Conferma |
|---|---|---|---|
| BUG-A | look-ahead classificazione bull/bear (gate 4) | CRITICAL | `repro_1_regime_lookahead.py` ✅ (controesempio) |
| BUG-B | `apply_regime_scale` dead code (mai chiamato) | MED | `repro_2_deadconfig.py` ✅ (ast, 0 call site) |
| BUG-C | reprice/SIGNAL_FLIP con IV di entry stale | HIGH | traccia statica ✅ |
| BUG-D | dead config (no from_yaml, no yaml file) | HIGH | `repro_2_deadconfig.py` ✅ (ast + glob) |
| BUG-E | accounting divergence (put P&L non nel NAV) | CRITICAL | `repro_3_accounting.py` ✅ (controesempio) |
| OBS-1..4 | filtro tautologico / gate5 triviale / capital hardcode / gate3 no-data | — | osservazioni |

**Nessun bug ha impatto runtime su capitale** (S2 disabled + hard-block, zero
attività DB). Tutti sono difetti di backtest/design; BUG-A e BUG-E invalidano
l'evidenza numerica interna; BUG-C distorce le uscite; BUG-B/D sono dead-code/
governance. L'azione è responsabilità dell'operatore e fuori freeze.

---
**Stato fase:** 07_bugs = **done**. Prossimo cursore: `S2:08_report`.