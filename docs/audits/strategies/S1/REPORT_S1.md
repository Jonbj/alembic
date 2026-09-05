# REPORT S1 — Multi-Lookback Relative Momentum

**Audit:** Alembic Strategy Audit · **Strategia:** S1 `TimeSeriesMomentum`
**Data report:** 2026-08-04
**Status:** `supervised_paper`, `approved=true` (lifecycle DB), `GLOBAL_LIVE_PROMOTION_ENABLED=False`
**Allocation:** 0.50 (unica sleeve con capitale assegnato)
**Fonti:** fasi 01–07 in `docs/audits/strategies/S1/`

---

## 1. Sintesi esecutiva

S1 è una strategia di **momentum multi-orizzonte, vol-normalizzato, z-score cross-sectionale, long-only**. Il nome (`TimeSeriesMomentum`) è fuorviante: **non è il TSMOM canonico di Moskowitz–Ooi–Pedersen (2012)** ma un ibrido TS/CS che combina un gate di momentum relativo con sizing inverso-vol.

**Verdetto alpha: `DECAYED + LIKELY_BETA`** — S1 non è, allo stato attuale, una fonte plausibile di alpha netto genuino. Cinque assi convergono:

1. **Decadimento**: il fattore momentum US è crollato da 0.92% a 0.16%/mese post-2002 (Ben-David et al. 2021) — nel mercato esatto di S1.
2. **Beta dominante**: la struttura long-only (no gamba short) rende S1 prevalentemente beta di mercato (~0.9) con un tilt momentum; l'alpha apparente collassa 6.1%→1.8% in un modello a 4 fattori (Israel-Ross 2017).
3. **Backtest invalido**: survivorship + look-ahead nella selezione universo + regime circolare + divergenza backtest↔live (BUG-2, BUG-3, OBS-3/OBS-4) → l'evidenza numerica di progetto non è attendibile.
4. **Design non allineato ai miglioramenti documentati**: nessun skip-month, nessun vol-scaling aggregato (BSC 2015 raddoppia lo Sharpe), gate binario che ignora la strength del segnale.
5. **Runtime in perdita**: S1 ha perso −$68.71 negli ultimi 7 giorni (15 trade, avg −$11.45) mentre S4 guadagnava +$145.40.

## 2. Specificazione (estratto — vedi `01_specification.md`)

- **Segnale**: per ogni lookback $l\in\{21,63,126,252\}$, $r_{t,l}=P_t/P_{t-l}-1$, normalizzato $\sigma_t=\sqrt{252}\,\mathrm{std}_{\mathrm{roll}}(63)$, pesi esponenziali $w_l\propto e^{\mathrm{rank}(l)}$ (252d pesa ~20× il 21d), aggregato, poi **z-score cross-sectionale** $S=(S-\bar S)/s$ (ddof=1).
- **Entry**: long i titoli con $S>0$ (soglia 0.0). **Long-only**, no short.
- **Sizing**: $w=\min(\text{target\_vol}/\sigma_{60}, 0.20)$, normalizzato a somma ≤1.0 per sleeve. **Il sizing NON scala con la strength del segnale** (gate binario).
- **Rebalance**: MONTHLY. Exit: posizioni assenti dal target.
- **Config effettivo**: `S1Config()` defaults (target_vol 0.10, max_weight 0.20) — NON il yaml (BUG-1).

## 3. Ipotesi scientifica (vedi `02_hypothesis.md`)

Scommette sull'**anomalia del momentum** (Jegadeesh-Titman 1993 CS; Moskowitz-Ooi-Pedersen 2012 TS). Le spiegazioni possibili: comportamentali (underreaction → alpha) vs risk-based (beta/compensazione). La struttura long-only di S1 la colloca sul lato **beta**.

## 4. Letteratura (vedi `03_literature.md` — 14 fonti citate)

- **Fondazione**: JT-1993, MOP-2012.
- **Repliche/contraddizioni**: Huang et al. 2020 (TSM debole asset-by-asset); Ahn et al. 2026 (rendimenti sovrapposti = artefatto); Grobys 2024 (critica power-law).
- **Decadimento**: Ben-David 2021 (momentum US 0.92→0.16%/mese post-2002).
- **Costi/capacità**: Frazzini-Israel-Moskowitz 2015 (~3%/anno, $56B); Patton-Weller 2020 (7.2–7.6%/anno per fondi tipici).
- **Regime/crash**: Daniel-Moskowitz 2016 (crash bear+rebound); Barroso-Santa-Clara 2015 (vol-scaling raddoppia Sharpe).
- **Alternative-beta**: Israel-Ross 2017, Roncalli 2017 (TSM = beta strategy); Brito-Ramos 2025 (long-only alpha netto possibile solo con filtro "pure trend" che S1 non ha).

## 5. Mappatura codice e divergenze (vedi `05_code_mapping.md`)

- Segnale: `signal.py:18-139` · Sizing: `sizing.py:8-40` · Selezione/norm: `strategy.py:87-153` · Rebalance: `strategy.py:177-268` · Live build: `portfolio_scheduler.py:3056-3068` · Stop: `execution.py:557,722-730`.
- **Divergenze**: D1 (target_vol) e D2 (sizing "∝signal") corrette nella documentazione da #490; D4 yaml non wired resta aperta.

## 6. Audit implementazione (vedi `06_implementation_audit.md`)

| Asse | Verdetto |
|---|---|
| Fill timing | ✅ T+1 (nota stale) |
| Look-ahead | ❌ FAIL (filtro universo full-window) |
| Survivorship | ❌ FAIL (non delisting-aware) |
| Backtest metodologia | ⚠️ PARTIAL (costi/T+1/manifest ok; regime circolare, DSR piccolo) |
| Backtest vs live | ⚠️ DRIFT (due codepath) |
| Risk controls | ⚠️ AMBER (stop off; d_hard breach su NOK) |
| Runtime | ⚠️ AMBER (S1 in perdita 7g) |

## 7. Bug confermati (vedi `07_bugs.md`)

| ID | Bug | Sev | Conferma |
|---|---|---|---|
| BUG-1 | `config/s1_strategy.yaml` dead config (non wired) | HIGH | `repro_1_deadconfig.py` ✅ |
| BUG-2 | Look-ahead selezione universo (filtro full-window) | CRITICAL | `repro_2_lookahead.py` ✅ (controesempio) |
| BUG-3 | Survivorship (universo non delisting-aware) | CRITICAL | traccia statica ✅ |
| BUG-4 | Note di demotion stale (t+0/zero-cost già fixati) | MED | traccia statica ✅ |
| BUG-5 | d_hard breach su posizione S1/NOK aperta (−22.99%), no catastrophe stop wired | HIGH | traccia DB ✅ |

**Riproduzioni eseguite 2026-08-04**:
- `repro_1`: 0 call site di `from_yaml` in `src/`; defaults == yaml → dead config latente.
- `repro_2`: alla data as_of=giorno50, il ticker C (delisted al giorno60) è incluso con pannello truncated ma escluso con pannello full (NaN futuri); lo z-score di A passa da −0.17 a −0.71 → il backtest usa informazione futura.

**Trace runtime**: posizione NOK/S1 aperta dal 2026-07-14 @ $11.72, ancora in essere, adverse 22.99%; 15 eventi `d_hard_breached` in 48h. La condizione di revisita di `trading.yaml` ("if any position rides past -15/20%") è **verificata e non indirizzata**.

## 8. Conclusioni e raccomandazioni (read-only — nessuna azione durante freeze)

S1 è **beta-dominata, su un'anomalia decaduta nel suo mercato, con backtest non attendibile e in perdita nel paper recente**. La promozione a live è correttamente bloccata. I bug confermati non richiedono azione durante il freeze 03/08→28/09; sono findings per l'operatore. Post-freeze, le condizioni che cambierebbero il verdetto:
1. Backtest rifatto con universo point-in-time (delisting-aware), filtro universo senza look-ahead, fill T+1, costi realistici, walk-forward OOS post-2010, DSR con n_trials grande.
2. Wire del d_hard catastrophe stop (la condizione è già verificata su NOK).
3. Valutazione del vol-scaling aggregato (BSC) e/o filtro pure-trend (Brito-Ramos) per il canale long-only.
4. Aggiornamento delle note di demotion in `config/strategies.yaml` (BUG-4) e wiring del yaml o rimozione del file morto (BUG-1).

Fino ad allora: **`DECAYED + LIKELY_BETA`**.
