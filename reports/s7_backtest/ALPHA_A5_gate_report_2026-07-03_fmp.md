# S7 PEAD — ALPHA-A5 Gate Report (FMP data source)

**Run date:** 2026-07-03
**Window:** 2026-01-01 – 2026-05-15 · **Events:** 76 BEAT / 20 MISS (of 97 with |surprise| ≥ 5%, 96 matched to price data)
**Harness:** `scripts/backtest_s7_pead.py` @ 04a9a28 (FMP data source; supersedes the Finnhub-based run in `ALPHA_A5_gate_report_2026-07-03.md`, which was INCONCLUSIVE — 0 events)

Raw run output: `reports/s7_backtest/ALPHA_A5_raw_output_fmp.txt`.

## Gate (ROADMAP_DATA_ALPHA_2026-07-02, ALPHA-A5)

| Criterio | Soglia | ALL | Large-cap | Small/mid-cap | Esito |
|---|---|---|---|---|---|
| BEAT drift 20d | ≥ +1.5% | +1.96% | +1.96% | n=0 | **FAIL** (hit-rate) |
| Hit-rate | > 55% | 51% | 51% | n=0 | **FAIL** |
| n (BEAT) | ≥ 30 | 76 | 76 | 0 | — |

**Verdetto: FAIL.** Il drift medio supera la soglia (+1.96% ≥ +1.5%), ma l'hit-rate (51%) è sotto la soglia richiesta (>55%) e anzi sotto il 50/50 — l'edge medio è positivo ma trainato da poche osservazioni con drift ampio più che da una direzionalità consistente trade-per-trade. Nessun evento small/mid-cap nel campione (tutti i 76 BEAT ricadono nel bucket large-cap ≥ $10B) — non è quindi possibile testare l'ipotesi "large-cap competuto, small/mid-cap con edge" della roadmap con questo universo di eventi.

MISS (contrarian short candidate, non nel gate primario): n=20, drift medio -0.13%, hit-rate 55% — troppo pochi eventi e drift quasi nullo per essere informativo.

## Come si è arrivati a un risultato conclusivo (da INCONCLUSIVE a FAIL)

Il run precedente (Finnhub) era INCONCLUSIVE per assenza totale di dati: il piano Finnhub attivo copre `calendar/earnings` solo ~30 giorni indietro. La roadmap specificava FMP come fonte, non ancora adottata. In questa sessione:

1. L'utente ha fornito una API key FMP (`FMP_API_KEY` in `.env`, aggiunta a `src/config.py`).
2. Verifica diretta: anche FMP free-tier **blocca il parametro `from`** su `/stable/earnings-calendar` (402 Payment Required, "Special Endpoint", qualunque valore) — stesso tipo di restrizione di Finnhub, non risolta dal solo cambio vendor.
3. Il parametro `to` (senza `from`) **è accessibile free-tier** e ritorna una finestra di record recenti prima del cutoff — ma **non monotona**: alcuni cutoff specifici ritornano batch vuoti anche quando cutoff sia precedenti che successivi ritornano dati (es. `to=2026-04-06/07` vuoto, `to=2026-04-01` e `to=2026-05-15` entrambi popolati e che coprono il gap).
4. Soluzione: `_fmp_earnings_paginated` cammina `to` all'indietro a **step fisso di 10 giorni** (non derivato dalla risposta precedente, per non far bloccare la ricerca su un cutoff "morto"). 15 chiamate coprono l'intera finestra richiesta; l'unica "dead zone" osservata (inizio aprile) è coperta dalle finestre di chiamate adiacenti.
5. Market cap: sostituito Finnhub `profile2` con FMP `/stable/profile`, con un cap di sicurezza (`_MAX_SYMBOLS_FOR_CAP=150`) contro la quota giornaliera FMP (~250 req/giorno, più stretta del rate-limit al minuto di Finnhub).

Nessuna delle richieste ha richiesto un piano a pagamento.

## Note metodologiche

- Entry: giorno di trading successivo all'annuncio (no look-ahead).
- Prezzi: Alpaca daily bars (IEX feed).
- Surprise: `(epsActual - epsEstimated) / abs(epsEstimated)`, soglia |surprise| ≥ 5%.
- Limiti: 66 simboli unici; 96/97 eventi con prezzo disponibile (1 scartato per assenza barre). Bucket large/small-mid da FMP `marketCap` (soglia $10B) — **zero eventi small/mid-cap nel campione**, quindi il confronto large-vs-small-cap della roadmap resta non testato, non "risolto a favore del large-cap".
- Il campione (76 BEAT) è concentrato nella finestra 2026-04-08–2026-05-13 (63/76 eventi, l'82%) perché quella è la porzione con densità di copertura FMP più alta nella query paginata — non un artefatto di selezione intenzionale, ma va tenuto presente nel leggere il risultato: non è un campione uniformemente distribuito sull'intera finestra Gen-Mag.

## Verdetto operativo

- **FAIL sul gate primario** (hit-rate). Drift medio positivo ma non sufficientemente diretto trade-per-trade.
- Small/mid-cap: **non testato** (0 eventi) — non si può concludere che l'alpha "esiste in un universo diverso" perché quell'universo non è stato campionato in questo run.
- Raccomandazione (da PO): S7 **non promuovere a paper trading** su questo risultato. Se si vuole testare l'ipotesi small/mid-cap, serve espandere l'universo di simboli monitorato oltre l'attuale, dato che con l'universo corrente FMP non ha restituito eventi small/mid-cap con |surprise|≥5%.
