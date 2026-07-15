# Prompt per Kimi 2.7-code — Stop-Loss Redesign (implementazione)

Sei un ingegnere senior. Implementa il redesign dello stop-loss di un sistema di
trading algoritmico live (Alembic, "Alpha Miner ATS"). Lavori nel repo (hai accesso ai
file). Questo prompt è autosufficiente per l'esecuzione; le decisioni di design sono
già prese — il tuo compito è implementarle fedelmente.

---

## 0. Prima di tutto — leggi questi due file del repo

1. `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md` — **il piano/spec
   completo**. È la fonte di verità: contesto, implementazione attuale verificata con
   `file:line`, design convergente, 7 fasi, schema SQL, config, test, gate, rollout.
2. `docs/stop_loss_review_prompt.md` — i dubbi D1-D9 e le risposte che hanno informato
   il design (con note dove l'audit ha corretto le premesse).

**Prima di editare, verifica che ogni `file:line` citato nello spec corrisponda al tuo
checkout** — usa `Agent(subagent_type="Explore")` per un fan-out read-only sui simboli
citati (lo spec è stato verificato 2026-07-11 su `main`; se il codice si è mosso, adatta
ma non cambiare la semantica). Non dare nulla per scontato dal tuo training: fonda ogni
assunzione sul codice che leggi nel repo.

---

## 1. Missione

Implementa le **7 fasi** dello spec nell'ordine di §13, **in autonomia dall'inizio alla
fine** (protocollo di decisione §3c: non bloccarti a fare domande, documenta e prosegui;
unica fermata hard = gate fase 6 FAIL). Alla fine **restituisci un handback strutturato**
(§10) che mi dà esattamente le info per il prossimo step — è un deliverable obbligatorio
esattamente come il codice.

1. Migration 034 (schema) → 2. Gap A (SELL decision sullo stop) → 3. StopPolicy +
   freeze-at-entry + log di stop + shadow log → 4. vol_scaled + stop-risk sizing
   (flag-off) → 5. disaccoppiamento ratchet S1↔S4 → 6. replay 15-min + gate →
7. runbook canary.

**Le fasi 1-4 sono codice puro (no gate di misura). La 5 è il refactor che gatinga il
live. La 6-7 sono misura/ops.**

---

## 1b. Skill & tooling — giri nel harness Claude Code

Sei in esecuzione nel **harness di Claude Code** (modello `kimi-k2.7-code:cloud` via
`ollama launch claude`). Hai il toolset completo (Read/Edit/Write/Bash, Agent, **Skill**)
e le **skill installate nel repo sono invocabili** via il tool `Skill`. La discipline
`superpowers:using-superpowers` è iniettata dal harness — seguila: **verifica le skill
prima di agire** (anche 1% di pertinenza → invocala).

### Skill da invocare (via `Skill`) ai momenti giusti
- **`codebase-design`** — quando disegni/scrivi `StopPolicy` (§4) e `LossFeedback` (§4b):
  deep modules, interface = test surface, deletion test. Vocabolario da usare in
  doc/commit: module / interface / implementation / depth / seam / adapter / leverage /
  locality (NON component/service/API/boundary).
- **`tdd`** — fasi 1-5: scrivi prima il test contro l'interfaccia del seed (§4 `compute`,
  §4b `threshold/record_exit`, §5 replay gates), vedi fallire, implementa, vedi passare.
  I seed danno già l'interfaccia → i test sono diretti. Fase 6 = test di misurazione
  (gate PASS/FAIL su storico, non TDD classico).
- **`domain-modeling`** — quando aggiorni `CONTEXT.md` e scrivi ADR (contenuto
  project-specific in §b2 sotto: la skill dà il processo, il prompt i termini).
- **`code-review`** (o l'agent `superpowers:code-reviewer`) — dopo ogni fase, prima del
  commit: review contro lo spec e gli standard del repo.

### Tooling da usare
- **`Agent(subagent_type="Explore")`** — verifica che i `file:line` dello spec
  corrispondano al tuo checkout prima di editare (lo spec è verificato al 2026-07-11).
- **`Bash`** — pytest, `scripts/audit_stop_loss_attribution.py`, git, `gh issue create`.
- **`superpowers:code-reviewer`** agent per la review post-fase.

### Issue tracker
Il repo traccia il lavoro come GitHub issues (`docs/agents/issue-tracker.md` + triage
labels in `docs/agents/triage-labels.md`, output del setup Matt Pocock). Se il team
traccia l'implementazione, crea una issue per fase con la triage label appropriata. Non
obbligatorio se lavori in locale senza push.

---

## 1c. Contenuto project-specific per `domain-modeling` (la skill non lo genera)

### b2-a. Termini da aggiungere a `CONTEXT.md` (glossary secco, zero dettagli
implementativi, formato esistente: termine → definizione + "avoid:" sinonimi sconsigliati)
- **Protective stop** — stop vol-scaled sintetico per-ciclo, congelato all'entry, per
  tagliare posizioni mal dimensionate. _Avoid:_ stop-loss (ambiguo col vecchio 2% fisso).
- **Broker disaster stop** — hard limit lato broker più largo, backstop di catastrofe,
  separato dal protective. _Avoid:_ hard stop (generico).
- **Frozen stop** — i parametri di stop (σ_eff, k, floor, cap, d_init) congelati
  all'entry sulla riga trade; lo stop non si allarga mai. _Avoid:_ static stop.
- **Stop-risk sizing** — il notionale si riduce all'allargarsi di d_init
  (`Notional ≤ NAV·B_s/(d+g)`) per tenere il rischio $ per posizione costante. _Avoid:_
  position sizing (generico).
- **R-multiple ratchet** — loss-feedback per-strategia, magnitudo-based su R-multiples
  (`R = net_pnl / risk_budget_at_entry`), non count-based. _Avoid:_ feedback loop.
Aggiorna i termini esistenti che il redesign muta: **Stop-loss cooldown** resta;
**Loss-feedback ratchet** va precisato "per-strategia, risk-normalizzato".

### b2-b. ADR — `docs/adr/` non esiste ancora; crealo al primo ADR
Formato: vedi `docs/agents/domain.md` per le regole consumer; nome file `NNNN-kebab.md`.
Scrivi ADR SOLO se tutti e tre: hard-to-reverse + sorprendente senza contesto + reale
trade-off (la skill `domain-modeling` detta il criterio). Candidati che soddisfano tutti
e tre (scrivine uno per ciascuna decisione che porti a termine):
- **ADR-1 — Three-layer stop separation** (strategy exit / protective / disaster) vs.
  un singolo "stop_loss": trade-off = più concetti vs. semantica coerente e attribuzione
  pulita; hard da invertire una volta che config/DB hanno i due nomi.
- **ADR-2 — Stop never widens; freeze-at-entry**: trade-off = rinuncia a trailing /
  re-calibrazione vs. proprietà di sicurezza (lo stop non si allarga mai); sorprendente
  per chi si aspetta un trailing.
- **ADR-3 — Measure-before-enforce for the stop (QX-01)**: il vol_scaled non va live finché
  i gate di replay passano; trade-off = slower rollout vs. no regressione non-misurata;
  sorprendente vs. "allarga lo stop e vai".
Non scrivere ADR per scelte effimere/ovvie (es. i valori numerici di k/floor/cap sono
prior, non decisioni architetturali).

---

## 2. Guardrail non-negoziabili (rispetta ABSOLUTAMENTE — spec §7)

1. **Nessun LLM / nessuna chiamata remota nel hot path.** Lo stop gira ogni 15 min nel
   ciclo: solo dati locali (bars_df, Redis, Postgres).
2. **Protective stop sempre sintetico, per-ciclo, uniforme** fractionable/whole-share.
   Non migrarlo mai al broker. Broker = disaster stop solo.
3. **Lo stop non si allarga mai** (long: trigger monotono non-crescente). Congela
   σ_eff/k/floor/cap/d_init all'entry sulla riga trade. (Il trailing è una fase dopo;
   fino ad allora il d_init congelato rende "never widens" vero per costruzione.)
4. **Una posizione per simbolo** (pyramiding guard P0-05). Lo stop lo assume; non
   rompere la guardia. Il match di `record_trade_exit` per simbolo è sicuro sotto
   questa invariante.
5. **Dietro flag, nessun cambio di comportamento di default.** `stop_loss_mode: fixed`
   è il default → identico all'odierno 2% finché non si passa a `vol_scaled`. Lo
   shadow log non invia MAI ordini.
6. **Path legacy (`execution.py`, `engine=legacy_sentiment`) invariato.** Aggiungi il
   modulo `StopPolicy` condiviso, ma NON cablarlo nel legacy in questa fase.
7. **Cooldown preservato** (`stop_loss_today` → mezzanotte UTC). La preoccupazione
   whipsaw S1 (blocca fino al next rebalance) è un sub-task DOPO; mantieni il
   comportamento attuale.
8. **`exit_reason` resta scritto al submit-time.** Non spostarlo nella riconciliazione.
9. **Measure before enforce (QX-01).** Nessuna misurazione stop live finché il gate di
   attribuzione (≥99% — già PASS) E i gate di replay (spec §10) non passano.
   Shadow-only fino ai gate.
10. **Tutti i test verdi** tranne gli 8 assert di `tests/workers/test_day1_fixes.py`
    che pinnano la vecchia firma — aggiornali. `scripts/audit_stop_loss_attribution.py`
    deve restare verde.

---

## 3. Ordine di esecuzione

### 3a. Pre-flight (fallo una volta, prima della fase 1)
1. Leggi i due doc del repo (§0). Verifica i `file:line` chiave via
   `Agent(subagent_type="Explore")`.
2. **Ambiente — scopri, non chiedere.** Determina autonomamente:
   - Come si lanciano i test: prova `.venv/bin/pytest -q` dal root; se non esiste,
     `pytest`, o `docker compose exec worker pytest` (leggi `docker-compose*.yml`).
     Annota cosa funziona e usalo per tutte le fasi.
   - DB raggiungibile: `DATABASE_URL` (`.venv/bin/python scripts/audit_stop_loss_attribution.py`
     deve uscire 0).
   - Come si applicano le migrazioni: leggi `migrations/apply_migrations.py` e come la
     `033` è registrata; replica per la `034`.
   - Branch: crea un branch di lavoro (`git checkout -b stop-loss-redesign`) da `main`;
     NON lavorare direttamente su `main`.
3. Esegui `audit_stop_loss_attribution.py` e la suite **una volta come baseline**:
   annota i conteggi (devono essere verdi prima di iniziare). Se la baseline non è
   verde, fermati e riportalo (non è colpa tua ma blocca tutto).

### 3b. Ciclo per fase
Per ogni fase: scrivi prima i test contro l'interfaccia del seed (`Skill tdd`) →
implementa → fai passare i test di quella fase → fai passare la suite completa →
**`Skill code-review`** (o agent `superpowers:code-reviewer`) review contro lo spec →
commit. **Non passare alla fase successiva se la suite non è verde.**

Dopo OGNI fase esegui entrambi (via `Bash`):
```
.venv/bin/python scripts/audit_stop_loss_attribution.py     # deve uscire 0 (gate ≥99%)
.venv/bin/pytest -q                                            # suite completa
```
(`audit_stop_loss_attribution.py` legge `DATABASE_URL`. Adatta l'invocazione di pytest
a quanto scoperto nel pre-flight.)

Commit per fase con conventional commits: `feat(stop): ...`, `refactor(ratchet): ...`,
`test(stop): ...`, `migrate(stop): 034 ...`. **Non pushare** a meno che non te lo
chiedano; lascia i commit locali sul branch.

### 3c. Protocollo di decisione — operazione autonoma
Sei autonomo dall'inizio alla fine: **non bloccarti a fare domande**, prendi decisioni
ragionevoli e documentale. Regole:
- **Spec `file:line` non corrisponde al checkout** → adatta minimamente preservando la
  semantica, logga in §10c. Non chiedere.
- **Dettaglio di ambiente ignoto** (invocazione pytest, container vs local, migration
  apply) → scopri leggendo il repo / provando (pre-flight 3a). Non chiedere.
- **Assunzione di implementazione arbitraria ma ragionevole** (modello di slippage nel
  replay, gap fill, H_max per strategia, mappa asset-class per il fallback σ_eff,
  finestra walk-forward) → scegline una ragionevole, documentala in §10c, prosegui.
- **Test che pinnava il vecchio comportamento** (§7.10, gli 8 di `test_day1_fixes`) →
  aggiornali al nuova interfaccia mantenendo `mode=fixed` che riproduce il 2%. Non
  conservare asserzioni stale.
- **UNICA fermata hard**: se uno **spec gate di fase 6 NON passa**, **FERMATI**: non
  forzare `vol_scaled`, non fare la canary. Riporta i numeri (§10b) e fermati — il
  passaggio a live è gated sui gate, non a tua discrezione.
- **Scelta ambigua AND load-bearing AND irreversibile** (raro) → scegli il default più
  sicuro, prosegui, e **elencala in §10i "Open questions"** perché la riveda l'umano. Non
  bloccare.

**NON cambiare `stop_loss_mode` a `vol_scaled` in `config/trading.yaml`** — lascia
`fixed` finché i gate di fase 6 non passano. La fase 4 implementa il supporto, non lo
abilita.

---

## 4. Seed — modulo `StopPolicy` (crea `src/portfolio/stop_policy.py` in fase 3)

Questo seed fissa l'interfaccia (la test surface). Crea il file con questa struttura;
implementa `compute()` (già fatto — banale, usa il d_init congelato) e `d_hard()`,
e implementa `freeze()` secondo lo spec §6.2/§6.3. Aggiungi la gerarchia di fallback
σ_eff (§6.3) e registra `vol_source`.

```python
# src/portfolio/stop_policy.py
"""Protective + disaster stop policy for the portfolio path (F9a redesign).

Deep module: all stop logic behind a small interface. The protective stop is
ALWAYS synthetic per-cycle and uniform across fractionable/whole-share (invariant
#2). The broker disaster stop (d_hard) is separate and wider.

Invariants enforced here (spec §7):
  - stop never widens (long: trigger monotonic non-increasing) — guaranteed because
    the protective trigger uses the FROZEN d_init, never recomputed from current vol.
  - freeze-at-entry: sigma_eff / k / floor / cap / d_init computed once at entry.
  - mode=fixed reproduces the legacy 2% (parity) so existing tests hold.

DO NOT call any LLM / remote API from here — this runs in the 15-min hot path.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FrozenStop:
    """Stop params frozen at entry; persisted on the trade row (migration 034)."""
    strategy: str | None        # "S1" | "S4" | "S7" | None
    mode: str                   # "fixed" | "vol_scaled"
    vol_at_entry: float | None  # sigma_eff at entry (None in fixed mode)
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    d_init: float               # clipped protective distance (legacy 0.02 in fixed mode)
    vol_source: str | None      # "bars_df" | "last_good" | "asset_median" | "tier" | "default"


@dataclass(frozen=True)
class StopDecision:
    """Result of one per-cycle protective check on one held position."""
    symbol: str
    strategy: str | None
    mode: str
    entry_price: float
    observed_price: float
    trigger_price: float        # entry_price * (1 - d_init) for a long
    d_init: float
    vol_at_entry: float | None
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    price_source: str            # "market.prices" | "bid" | ...
    vol_source: str | None
    breached: bool
    cycle_ts: datetime


class StopPolicy:
    """One policy, two modes. The protective stop is synthetic per-cycle.

    Interface (the test surface — tests/portfolio/test_stop_policy.py):
      freeze(symbol, strategy, entry_price, cycle_ts) -> FrozenStop
      compute(symbol, entry_price, observed_price, frozen, cycle_ts, price_source) -> StopDecision
      d_hard(symbol, frozen, sigma_eff_current) -> float
    """

    def __init__(self, risk_cfg: dict, bars_df) -> None:
        self._cfg = risk_cfg
        self._bars = bars_df  # pivoted close: index=timestamp, columns=symbol
        # Precompute per-symbol sigma_eff from bars_df pct_change:
        #   sigma_eff = max(EWMA20(daily ret), 0.8 * STD63(daily ret))   # daily, NOT annualized
        # (lookbacks from risk_cfg: stop_sigma_lookback_fast/slow, stop_sigma_ewma_floor_ratio)

    # --- strategy params lookup ---
    def _params(self, strategy: str | None) -> tuple[float, float, float]:
        """Return (k, floor, cap) for the strategy, falling back to 'default'."""
        params = self._cfg.get("stop_strategy_params", {})
        p = params.get(strategy) or params.get("default") or {"k": 3.0, "floor": 0.04, "cap": 0.12}
        return float(p["k"]), float(p["floor"]), float(p["cap"])

    # --- sigma_eff with fallback hierarchy (spec §6.3) ---
    def _sigma_eff(self, symbol: str) -> tuple[float | None, str]:
        """Return (sigma_eff, vol_source). Fallback: bars_df -> last_good ->
        asset_median -> tier (config/cost_model.yaml) -> default."""
        # 1. bars_df if present with >= fast lookback bars
        # 2. last-good (<=5 sessions) from stop_vol_history/Redis
        # 3. median per asset class
        # 4. liquidity tier table
        # 5. default (use default-strategy params, vol_source="default")
        raise NotImplementedError

    def freeze(self, symbol: str, strategy: str | None,
               entry_price: float, cycle_ts: datetime) -> FrozenStop:
        """Compute + freeze stop params at entry. Persist the result on the trade row.

        mode=fixed  -> d_init = risk_cfg['stop_loss'] (0.02), vol fields None.
        mode=vol_scaled -> sigma_eff via _sigma_eff; d_init = clip(k*sigma_eff, floor, cap).
        """
        mode = self._cfg.get("stop_loss_mode", "fixed")
        if mode == "fixed":
            return FrozenStop(strategy=strategy, mode="fixed", vol_at_entry=None,
                              sigma_eff=None, k=None, floor=None, cap=None,
                              d_init=float(self._cfg.get("stop_loss", 0.02)),
                              vol_source=None)
        k, floor, cap = self._params(strategy)
        sigma_eff, vol_source = self._sigma_eff(symbol)
        d_init = min(max(k * (sigma_eff or 0.0), floor), cap)
        return FrozenStop(strategy=strategy, mode="vol_scaled", vol_at_entry=sigma_eff,
                          sigma_eff=sigma_eff, k=k, floor=floor, cap=cap,
                          d_init=d_init, vol_source=vol_source)

    def compute(self, symbol: str, entry_price: float, observed_price: float,
                frozen: FrozenStop, cycle_ts: datetime,
                price_source: str = "market.prices") -> StopDecision:
        """Per-cycle protective check. Uses ONLY frozen.d_init -> never widens."""
        trigger = entry_price * (1.0 - frozen.d_init)
        return StopDecision(
            symbol=symbol, strategy=frozen.strategy, mode=frozen.mode,
            entry_price=entry_price, observed_price=observed_price,
            trigger_price=trigger, d_init=frozen.d_init,
            vol_at_entry=frozen.vol_at_entry, sigma_eff=frozen.sigma_eff,
            k=frozen.k, floor=frozen.floor, cap=frozen.cap,
            price_source=price_source, vol_source=frozen.vol_source,
            breached=observed_price <= trigger, cycle_ts=cycle_ts,
        )

    def d_hard(self, symbol: str, frozen: FrozenStop,
               sigma_eff_current: float | None) -> float:
        """Broker disaster stop distance. Wider than d_init. clip([floor_pct, cap_pct])."""
        cfg = self._cfg.get("broker_disaster_stop", {})
        mult = float(cfg.get("multiplier", 1.5))
        sig_mult = float(cfg.get("sigma_multiple", 5.0))
        floor = float(cfg.get("floor_pct", 0.12))
        cap = float(cfg.get("cap_pct", 0.20))
        base = max(mult * frozen.d_init, sig_mult * (sigma_eff_current or 0.0))
        return min(max(base, floor), cap)
```

**Test da scrivere** (`tests/portfolio/test_stop_policy.py`) — questa è la test surface:
- `mode=fixed` riproduce la soglia 2% (parità con legacy) → mantiene valide le
  asserzioni di `test_day1_fixes` in fixed mode.
- `mode=vol_scaled`: `d_init = clip(k*sigma_eff, floor, cap)`; titolo alta-vol → cap,
  bassa-vol → floor.
- **never-widens**: due `compute()` con σ corrente crescente → stesso `trigger`
  (d_init congelato).
- gerarchia di fallback: simbolo assente da bars_df → `vol_source` riflette il tier usato.
- `d_hard >= d_init` e clippato a [12%, 20%].
- round-trip `freeze` → `compute`.

---

## 4b. Seed — ratchet per-strategy risk-normalizzato (fase 5)

Oggi il ratchet è **spaccato** tra `performance.py` (scrive `feedback:entry_threshold` +
`feedback:regime_scale` alle righe `:1607-1608`, `:1728-1729`) e `portfolio_scheduler.py:582-600`
(`_get_feedback_threshold` legge la **singola** chiave `feedback:entry_threshold` come hard
gate S4). Problemi: (1) cross-strategy — una perdita S1 alza la soglia di ingresso S4;
(2) count-based — una perdita −0.2R conta come una −3R; (3) `feedback:regime_scale` è
orphaned (F8). Consolida in un **deep module** `src/workers/loss_feedback.py` con read /
record / decay dietro un'interfaccia unica (la test surface).

Crea `src/workers/loss_feedback.py`:

```python
# src/workers/loss_feedback.py
"""Per-strategy, risk-normalized loss-feedback ratchet (F9a phase 5).

Deep module consolidating the ratchet (previously split: performance.py wrote
feedback:entry_threshold, portfolio_scheduler.py:582-600 read it). One module, one
interface, tested through it.

Redesign rationale (spec phase 5): the old ratchet was cross-strategy + count-based:
  - an S1 stop-out raised the S4 entry threshold (cross-contamination)
  - a -0.2R loss counted the same as a -3R loss
Now:
  - per-strategy keys: feedback:entry_threshold:S1 / :S4 / :S7
  - magnitude-based: EWMA of R-multiples, R = net_pnl / risk_budget_at_entry,
    risk_budget_at_entry = d_init_frozen * entry_notional  (from the frozen stop, §4)
  - exit-reason filter: only realized strategy losses (stop_loss, portfolio_sell)
    teach the ratchet; LEGACY_FLATTEN / sentiment_reversal / operational excluded
  - decay: threshold decays toward baseline on wins; 48h TTL preserved (spec §2).

NO LLM / no remote. The read side runs every 15-min cycle (hot path).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

# Only these exit reasons teach the ratchet (realized strategy losses). A
# capital-protection exit (sentiment_reversal) or operational flatten is NOT a
# thesis failure and must not poison the threshold.
TEACHING_REASONS: frozenset[str] = frozenset({"stop_loss", "portfolio_sell"})


@dataclass(frozen=True)
class FeedbackState:
    strategy: str
    threshold: float          # current entry threshold for the strategy
    baseline: float           # baseline threshold (e.g. S4=0.30; S1 has no gate)
    ewma_r: float | None       # last EWMA of R-multiples (None until first exit)
    updated_at: datetime | None


class LossFeedback:
    """Per-strategy risk-normalized ratchet. Interface (test surface):

      threshold(strategy) -> float                                  # hot path, every cycle
      record_exit(strategy, exit_reason, net_pnl, risk_budget) -> None
      decay(strategy) -> None                                        # on wins / time
    """

    KEY_THRESH = "feedback:entry_threshold:{strategy}"   # float
    KEY_EWMA   = "feedback:ewma_r:{strategy}"            # float (EWMA state)
    TTL_SECONDS = 48 * 3600

    def __init__(self, redis_url: str, cfg: dict) -> None:
        self._redis_url = redis_url
        self._cfg = cfg                                # loss_feedback section + per-strategy baselines
        # per-strategy baseline thresholds: e.g. {"S4": 0.30, "S1": 0.0, "S7": 0.25}
        self._baselines = cfg.get("feedback", {}).get("threshold_baselines", {"S4": 0.30})
        self._alpha = float(cfg.get("feedback", {}).get("ewma_alpha", 0.3))   # EWMA weight
        self._raise_band = float(cfg.get("feedback", {}).get("raise_band_r", -1.0))  # EWMA(R) < this -> raise
        self._raise_step = float(cfg.get("feedback", {}).get("raise_step", 0.05))     # +threshold per band breach

    def threshold(self, strategy: str) -> float:
        """Read the current entry threshold for a strategy (hot path).
        Returns baseline if key absent/expired, or for strategies without a gate
        (S1 continuous rebalance has no discrete entry threshold -> returns 0.0)."""
        # r.get(KEY_THRESH) or baseline; S1 baseline 0.0 (no gate).
        raise NotImplementedError

    def record_exit(self, strategy: str, exit_reason: str, net_pnl: float,
                    risk_budget_at_entry: float) -> None:
        """Called when a trade closes. No-op if exit_reason not in TEACHING_REASONS
        or risk_budget_at_entry <= 0. Otherwise:
          R = net_pnl / risk_budget_at_entry       # a -3R loss is 15x a -0.2R loss
          ewma_r = alpha*R + (1-alpha)*prev_ewma_r
          if ewma_r < raise_band: threshold = min(threshold + raise_step, max_threshold)
        Persist both keys with TTL. Positive R (wins) also nudges toward decay."""
        if exit_reason not in TEACHING_REASONS or risk_budget_at_entry <= 0:
            return
        raise NotImplementedError

    def decay(self, strategy: str) -> None:
        """Move threshold toward baseline. Called on wins / scheduled. Preserve 48h TTL:
        if a strategy has had no teaching exits for 48h, the key expires -> baseline."""
        raise NotImplementedError
```

**Wire points:**
- **Read:** `portfolio_scheduler.py:582-600` `_get_feedback_threshold` → delega a
  `LossFeedback.threshold(strategy)`; la soglia S4 usa `threshold("S4")`. S1 non ha gate
  (rebalance continuo) → `threshold("S1")` restituisce 0.0 / no-op. La chiave legacy
  `feedback:entry_threshold` (senza suffisso) va deprecata: durante la transizione leggila
  come fallback per S4 se la nuova chiave `:S4` non esiste (backward-compat con stati Redis
  pre-migrazione).
- **Write:** `performance.py:1607-1608` / `:1728-1729` → delega a
  `LossFeedback.record_exit(strategy, exit_reason, net_pnl, risk_budget)`. La strategia si
  deriva dall'exit come in trading.py:96-103 (S4 se signal_id presente sul trade, S1
  altrimenti). `risk_budget_at_entry = d_init * entry_notional` letto dalla riga trade
  (le colonne `stop_d_init` + `entry_notional` della migration 034). `net_pnl` dalla riga
  trade chiusa (escludi `net_pnl` NULL — M7).
- **Decay:** programma un decay periodico (es. nel daily report) o on-win;
  `feedback:regime_scale` (F8, orphaned) — NON cablarlo in questa fase; lascialo scrivere
  com'è per il path legacy, ma il portfolio path non lo legge (confermato).

**Config** (aggiungi a `config/trading.yaml` → `feedback:`):
```yaml
feedback:
  enabled: true
  threshold_baselines: {S4: 0.30, S7: 0.25}   # S1 omesso -> 0.0 (no gate)
  ewma_alpha: 0.3                              # EWMA weight on R-multiples
  raise_band_r: -1.0                           # raise threshold when EWMA(R) < -1.0
  raise_step: 0.05                             # +5% threshold per band breach
  max_threshold: 0.60
  ttl_hours: 48
```

**Test** (`tests/workers/test_loss_feedback.py`):
- Una perdita S1 alza `feedback:entry_threshold:S1` ma NON `:S4` (no cross-contamination).
- Una perdita S1 di −3R alza la soglia S1 **più di** una −0.2R (magnitudo, non count).
- Un exit `LEGACY_FLATTEN` non muove nessuna soglia.
- Un exit `sentiment_reversal` non muove nessuna soglia.
- `decay` avvicina la soglia al baseline; dopo 48h senza teaching exits la chiave scade → baseline.
- S1 `threshold()` restituisce 0.0 (no gate).
- Backward-compat: se esiste solo la chiave legacy `feedback:entry_threshold`, S4 la usa come fallback.

---

## 5. Seed — harness di replay (fase 6) — `scripts/replay_stop_loss.py`

Read-only/idempotent (pattern di `scripts/validate_ticker_sentiment.py`). La fase più
ambigua — parte da questo scheletro. Scarica bar Alpaca storiche a 15-min (o più fine)
per le finestre entry→exit dei trade chiusi, ricostruisci i trigger fixed vs vol_scaled
(vol congelata all'entry come sarebbe stata calcolata allora), classifica false-stop /
MAE / MFE, confronta le varianti, walk-forward, valuta i gate.

```python
# scripts/replay_stop_loss.py  (skeleton)
#!/usr/bin/env python3
"""Replay storico dello stop-loss (F9a, measure-before-enforce).

Per ogni trade chiuso (trades.exit_time IS NOT NULL, net_pnl NOT NULL — esclude i
trade M7 con net_pnl NULL), ricostruisce su bar Alpaca 15-min:
  - trigger_fixed    = entry * (1 - stop_loss_fixed)
  - trigger_vol_scaled = entry * (1 - clip(k_strat * sigma_eff_at_entry, floor, cap))
    con sigma_eff calcolato sulle daily bar disponibili ALLA DATA DI ENTRY (no look-ahead).
Classifica:
  false_stop_s1  : fermato ma prezzo torna sopra entry (o sopra exit, o P&L > 0)
                   prima del next rebalance / invalidazione segnale.
  false_stop_s4  : fermato ma prezzo torna positivo entro l'event window.
  mae/mfe        : vol-normalized, time-to-stop, slippage, gap loss oltre soglia.
Confronta varianti: 2%, 3%, 5%, 7%, vol_scaled(k=2.5/3/3.5/4), ATR(14)*k, no-protective,
  strategy-exit-only. WALK-FORWARD: NON selezionare e valutare sullo stesso periodo.

Gate (spec §10) — stampa PASS/FAIL per ciascuno:
  false-stop reduction >= 40% vs fixed 2%
  median net P&L > fixed 2%
  delta P&L positivo in >= 70-75% dei bootstrap resamples
  portfolio max-DD non > 10% peggiore
  ES95 non > 10% peggiore
  costi/slippage inclusi
  open-stop risk entro budget
  risultato non dipendente da 1-2 nomi

Read-only. Non scrive su DB. Esce non-zero se un gate critico fallisce (definisci
quali sono critici nella PR).
"""
from __future__ import annotations
import os
# psycopg2, pandas, alpaca-py (historical bars), numpy per bootstrap.

# 1) carica trade chiusi con net_pnl NOT NULL (escludi M7 + LEGACY_FLATTEN).
# 2) per ogni trade: entry_time, exit_time, symbol, entry_price, exit_price, qty,
#    signal_id (-> strategy via origin logic: S4 if signal_id else S1), net_pnl.
# 3) fetch daily bar fino all'entry per sigma_eff_at_entry (no look-ahead);
#    fetch 15-min bar in [entry_time, min(exit_time, entry_time+H_max)].
# 4) per ogni variante: trova primo timestamp in cui low <= trigger -> stop_time,
#    exit_fill = min(trigger*(1-slip), bar_open_next) per stimare slippage/gap.
# 5) calcola P&L della variante vs il P&L reale (fixed 2%) e vs strategy-exit-only.
# 6) false-stop, MAE/MFE, metriche aggregate, bootstrap, gate PASS/FAIL.
```

Implementa completamente; documenta le assunzioni (gap fill, slippage model, H_max per
strategia). Se un'assunzione è arbitraria, scegline una ragionevole e segnala nella PR.

---

## 6. Comandi & ambiente (verifica nel repo)

- Python: `.venv/bin/python` (ha psycopg2, alpaca-py). Tests: `.venv/bin/pytest -q`
  (verifica la root dei test / pytest.ini).
- DB: `DATABASE_URL=postgresql://trading:trading@localhost:5432/trading`
  (in-container: `postgres:5432`). Live su `alembic-postgres-1`.
- Migrazioni: `migrations/apply_migrations.py` — studia come la 033 è registrata e
  aggiungi la 034 allo stesso modo. Tutte `IF NOT EXISTS` (idempotenti).
- Alpaca keys: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL` in `.env`
  (feed iex). Per le bar storiche 15-min usa lo stesso client.
- Config: `config/trading.yaml` (sezione `risk:`), `config/cost_model.yaml` (tier table
  legacy, usala come fallback σ_eff livello 4).

---

## 7. Definition of done (per fase) — spec §12 checklist

- [ ] **P1** `034_stop_loss_redesign.sql` applica pulito (idempotente); colonne/tabelle
      nuove esistenti.
- [ ] **P2** Lo stop scrive una riga `execution_decisions` SELL; Decision Log mostra gli
      stop (0/11 → 11/11 sulle nuove).
- [ ] **P3** `StopPolicy` testato; freeze-at-entry persistito sui nuovi trade;
      `stop_decisions` riga su ogni fire; `stop_shadow_log` righe a flag on (nessun
      ordine). Test never-widens passa. `mode=fixed` riproduce 2%.
- [ ] **P4** `vol_scaled` + stop-risk sizing cablati; d_init più largo → qty più
      piccolo; default resta `fixed`; suite verde.
- [ ] **P5** Perdita S1 muove solo `feedback:entry_threshold:S1`; basata su magnitudo
      (R-multiples); exit operativi esclusi; decade sui win.
- [ ] **P6** `replay_stop_loss.py` gira; tutti i gate passano su walk-forward OOS.
- [ ] **P7** Runbook canary S1 10% budget; ≥20 exit, zero anomalie, vecchio stop in
      shadow.
- [ ] `scripts/audit_stop_loss_attribution.py` verde dopo ogni fase.
- [ ] Nessuna chiamata LLM/remote aggiunta al ciclo 15-min.
- [ ] Tutti i test verdi tranne gli 8 assert aggiornati di `test_day1_fixes`.

---

## 8. Cosa NON fare (out of scope — spec §11)

- Virtual sleeve accounting (1-position-per-symbol tiene; non serve per v1).
- Trailing stop (fase dopo; d_init congelato fino ad allora).
- Migrare il protective stop al broker (fractional simple stops). Resta sintetico.
- Cambiare il comportamento del path legacy (`execution.py`).
- Entry filter (decelerazione / reversal breve termine) — workstream separato.
- Cooldown S1 → next-rebalance (mantieni mezzanotte UTC).
- Calibrazione k su MAE per S7 (S7 non live; usa il prior).
- Moltiplicatore `sqrt(holding_days)` — esplicitamente rifiutato (spec §6.2).
- Abilitare `stop_loss_mode: vol_scaled` in `config/trading.yaml` (lascia `fixed`).

---

## 9. Consegna

- Un commit per fase (conventional commits). Non pushare a meno che richiesto.
- **`Skill domain-modeling`**: aggiungi i 5 termini di §1c a `CONTEXT.md` (man mano che
  li introduci); scrivi gli ADR-1/2/3 di §1c quando le rispettive decisioni sono a regime.
- **`Skill code-review`** (o agent `superpowers:code-reviewer`) dopo ogni fase, prima
  del commit.
- Nella PR/descrizione finale: per ogni fase, output di `audit_stop_loss_attribution.py`
  + `pytest -q` (riassunto pass/fail), e l'esito dei gate di fase 6.
- Segnala esplicitamente ogni `file:line` dello spec che non corrispondeva al checkout e
  come lo hai adattato.
- Se uno spec gate di fase 6 NON passa, NON forzare `vol_scaled`: riporta i numeri e
  fermati (il passaggio a live è gated sui gate, non a tua discrezione).

Inizia dalla fase 1. Leggi i due doc del repo (§0) e invoca le skill di §1b prima di
scrivere codice.

---

## 10. Return contract — cosa devi restituire alla fine (OBBLIGATORIO)

Alla fine (o se ti fermi al gate di fase 6), **scrivi un file di handback** e stampa un
riassunto. Il file mi dà esattamente le info per il prossimo step senza che io debba
ricostruirle.

**File:** `docs/stop_loss_kimi_handback.md` (sovrascrivi se esiste). Struttura esatta:

```markdown
# Stop-Loss Redesign — Handback (Kimi → Claude)
**Data:** <YYYY-MM-DD>  **Branch:** <nome>  **Commit ultimo:** <hash>
**Baseline suite:** <pass/fail prima di iniziare>

## a. Stato per fase
| Fase | Status | Commit | Test (pass/total) | Audit gate | Note |
|-----|--------|--------|-------------------|-----------|------|
| 1 migration 034 | done\|partial\|blocked | <hash> | n/n | PASS 100% | ... |
| 2 Gap A decision log | ... |
| 3 StopPolicy + freeze + logs | ... |
| 4 vol_scaled + sizing (flag-off) | ... |
| 5 ratchet decouple S1↔S4 | ... |
| 6 replay + gate | ... |
| 7 canary runbook | ... |
(Status: done / partial / blocked / skipped. Per blocked: motivo in una riga.)

## b. Risultati gate di fase 6 (CRITICO — decide se vol_scaled può andare live)
- false-stop reduction vs fixed 2%: **<X%>** (gate ≥40%) → PASS/FAIL
- median net P&L: fixed <X> vs vol_scaled <X> (gate vol_scaled > fixed) → PASS/FAIL
- bootstrap delta P&L positivo: **<X%>** dei resamples (gate ≥70-75%) → PASS/FAIL
- portfolio max-DD: <delta> (gate non >10% peggiore) → PASS/FAIL
- ES95: <delta> (gate non >10% peggiore) → PASS/FAIL
- costi/slippage inclusi: sì/no
- open-stop risk: <X> bp vs budget <Y> bp → entro/out
- name-dependence: <top-2 contrib %>
- Variante raccomandata (se i gate passano): k=< > floor=< > cap=< > per strategia, con
  split walk-forward usato (train/test date). Se i gate NON passano: "GATE FAIL — fermo".
- Shadow log: <N> sessioni, <M> divergence events fixed vs vol_scaled (gate ≥30 e ≥30).

## c. Decisioni prese in autonomia (con rationale)
- <decisione> — <perché>. (es. "slippage model = 5 bps linear sul notional perché è il
  default del cost_calc del repo", "H_max S1 = 21 giorni = lookback minimo", "fallback
  asset-class map = {equity: ..., ETF: ...} perché S2/S7 non live", "walk-forward split
  70/30 sulle date entry...")

## d. Discrepanze file:line spec vs checkout
- spec <file:line> diceva <X>, nel checkout è <Y> → adattato preservando semantica come <Z>.

## e. Artefatti di dominio
- CONTEXT.md: aggiunti i termini <lista>. (Se non li hai aggiunti: perché.)
- ADR: <path> — <titolo, una riga>. (Se non scritti: perché — es. decisione non ancora a regime.)

## f. Config / migration
- `migrations/034_stop_loss_redesign.sql`: applicata al DB live? sì/no (se no, comando
  per applicarla).
- `config/trading.yaml`: nuove chiavi aggiunte, `stop_loss_mode` rimasto `fixed`? sì/no.
- Branch: pushato? sì/no. Commit locali non pushati: <lista hash>.

## g. Cosa non è completo / bloccato
- <fase o sub-task> — <motivo>. (es. "fase 7 canary non eseguita: gate fase 6 FAIL")

## h. Readiness canary (se fase 7 raggiunta, anche solo runbook)
- Pronto per paper S1 10%? sì/no + cosa manca (es. "≥20 exit non ancora raccolte nel
  shadow — servono N sessioni in più").

## i. Open questions per l'umano (decisioni load-bearing che rivedi)
- <domanda> — <default sicuro che hai usato nel frattempo>. (Solo scelte ambigue AND
  load-bearing AND irreversibili. Se nessuna: "nessuna".)

## j. Come riprendere (prossimi comandi)
- Prossimo step suggerito: <es. "rivedere i gate fase 6 in §10b; se PASS, abilitare
  vol_scaled in config/trading.yaml su paper e avviare canary S1 10%">.
- Comandi: `git log --oneline -10` sull'handback, `.venv/bin/pytest -q`,
  `cat docs/stop_loss_kimi_handback.md`.
```

**In più**, stampa un riassunto (≤30 righe) a video alla fine con: status per fase (a),
gate fase 6 (b) in evidenza, e "PROSSIMO STEP: <j>". Se ti sei fermato al gate FAIL,
il riassunto deve dirlo esplicitamente in cima.

Questo handback è il tuo deliverable finale insieme al codice. Senza di esso non posso
proseguire — non ometterlo nemmeno se tutto è andato liscio.