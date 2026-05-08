---
name: Multi-Asset News-Driven — Brainstorming in corso
description: Stato del brainstorming per la feature multi-asset news-driven (2026-05-08)
type: project
originSessionId: d463b4ac-a870-4ca6-91e4-f2b227e2688e
---
## Stato: brainstorming in corso — domande chiarificatrici

**Idea:** passare da architettura symbol-driven (lista fissa → fetch news per simbolo → sentiment) a **news-driven** (news generiche → estrazione ticker automatica → sentiment → segnale per quel simbolo). Nessuna watchlist fissa.

**Contesto codebase:**
- `config/trading.yaml` ha già `symbols.watchlist` con 9 simboli MA non è connesso a `config.py`
- `src/workers/performance.py:58` hardcoda 6 simboli per i calcoli IC
- `src/workers/sentiment.py` legge già da `news:queue` Redis → agnostico sui simboli
- `quantconnect/intraday_strategy.py` accetta override via parametro QC
- Non esiste un task Celery che popola `news:queue` — la coda è popolata esternamente

**Tre approcci per estrazione ticker (da presentare all'utente):**

A. **LLM extraction** — estende il prompt DK-CoT con campo `"symbol"` nell'output JSON. Nessun componente extra. Rischio: LLM può sbagliare ticker.

B. **GDELT entity tags + lookup table** — GDELT fornisce già tag organizzazioni. Lookup table `{nome azienda → ticker}` (S&P 500 + indici). Nessuna chiamata extra, serve mantenere la lookup.

C. **NER dedicato** — FinBERT-NER o spaCy finance estrae entità organizzative, poi lookup a ticker. Più robusto ma aggiunge dipendenza e latenza.

**Prossimo passo:** l'utente deve rispondere quale approccio preferisce per l'estrazione ticker.

**Why:** sessione interrotta per cambio macchina. Riprendere da qui.

**How to apply:** Alla prossima sessione, leggere questo file e riprendere il brainstorming dal punto in cui l'utente sceglie l'approccio A/B/C.
