# S7 PEAD — ALPHA-A5 Gate Report

**Run date:** 2026-07-03
**Window:** 2026-01-01 – 2026-05-15  ·  **Events:** 0 BEAT / 0 MISS
**Harness:** scripts/backtest_s7_pead.py @ e55d568

## Gate (ROADMAP_DATA_ALPHA_2026-07-02, ALPHA-A5)
| Criterio | Soglia | Large-cap | Small/mid-cap | Esito |
|---|---|---|---|---|
| BEAT drift 20d | ≥ +1.5% | n=0 | n=0 | **INCONCLUSIVE** |
| Hit-rate | > 55% | n=0 | n=0 | **INCONCLUSIVE** |

Raw run output: `reports/s7_backtest/ALPHA_A5_raw_output.txt`.

## Verdetto

**Non è possibile valutare il gate ALPHA-A5: 0 eventi earnings con dati sufficienti nella finestra richiesta.** Non è un FAIL (nessuna evidenza che PEAD non funzioni) né un PASS — è un blocco sui dati sorgente, non sulla strategia.

### Causa accertata

L'harness interroga `Finnhub /calendar/earnings` per la finestra 2026-01-01..2026-05-15. La chiamata HTTP ritorna `200 OK` ma con `earningsCalendar: []` per l'intera finestra. Verifica diretta contro l'API (fuori dall'harness) mostra che il piano Finnhub in uso copre solo una finestra storica ristretta:

| Finestra testata | Eventi |
|---|---|
| 2026-01-01 → 2026-05-15 (finestra del gate) | 0 |
| 2026-05-15 → 2026-05-29 | 0 |
| 2026-06-01 → 2026-06-14 | 186 |
| 2026-06-15 → 2026-06-19 | 112 |

Il confine cade tra il 2026-05-29 e il 2026-06-01: il piano Finnhub attivo copre solo **~30 giorni indietro da oggi**, non l'anno richiesto dal gate. Questo è coerente con la limitazione nota del free/basic tier di Finnhub su `calendar/earnings` (storico esteso è a pagamento).

### Nota sul disallineamento harness/roadmap

`docs/ROADMAP_DATA_ALPHA_2026-07-02.md` §ALPHA-A5 specifica esplicitamente **"backtest 1 anno FMP"** come fonte dati per questo gate. L'harness committato (694df3b) usa invece Finnhub. La scelta vendor (FMP vs multi-vendor) è tra le **decisioni riservate al PO** (stop point §9.2 della roadmap) — non è stata presa unilateralmente qui, né in questa sessione né nell'harness originale.

## Percorsi per sbloccare il gate (decisione PO)

1. **Upgrade Finnhub** a un piano con storico esteso su `calendar/earnings` (verificare se copre l'intero anno richiesto).
2. **Adottare FMP** per questo backtest, come originariamente previsto dalla roadmap (richiede API key FMP, non presente in `.env` al momento del run).
3. **Restringere la finestra del gate** al periodo effettivamente coperto dal piano Finnhub corrente (~30gg) — insufficiente per una valutazione statisticamente solida (il gate richiede n≥30 eventi BEAT per bucket; una finestra di 30gg ne produce una frazione, non ripartibile in modo affidabile per large vs small/mid-cap).

Nessuna di queste è stata eseguita: sono decisioni vendor/budget riservate al PO (regola di ingaggio #3 del piano di remediation).

## Note metodologiche

- Entry: giorno di trading successivo all'annuncio (no look-ahead) — invariato, non eseguito per assenza di eventi.
- Prezzi: Alpaca daily bars (IEX feed) — non raggiunti (0 simboli da cui recuperare barre).
- Limiti: harness eseguito senza modifiche di codice (nessun crash, nessun fix necessario); il blocco è a monte, sulla sorgente dati earnings calendar.
