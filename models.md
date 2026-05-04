# Modelli disponibili e testati

**Ultimo aggiornamento:** 2026-05-03  
**Metodo:** Test diretto con `claude -p --model <nome> "OK"`

---

## ✅ Modelli funzionanti (testati e verificati)

### Modelli General Purpose

| Modello | Tipo | Note |
|---|---|---|
| `sonnet` | Claude | Alias Anthropic — USATO per analisi |
| `opus` | Claude | Alias Anthropic — USATO per analisi |
| `haiku` | Claude | Alias Anthropic — Testato OK |
| `qwen3.5:cloud` | Qwen | Cloud — USATO per analisi |
| `deepseek-v4-pro:cloud` | DeepSeek | Cloud — Testato OK |
| `glm-5.1:cloud` | GLM | Cloud — USATO per analisi |
| `kimi-k2.6:cloud` | Kimi | Cloud — USATO per analisi |
| `gemma4:31b-cloud` | Gemma | Cloud — USATO per analisi |

### Modelli Specifici per Coding ⭐

| Modello | Tipo | Note |
|---|---|---|
| `qwen3-coder-next:cloud` | Qwen Coder | **FUNZIONA** — Coding specializzato |
| `devstral-small-2:24b-cloud` | Devstral | **FUNZIONA** — 24B parametri, coding |
| `devstral-2:123b-cloud` | Devstral | **FUNZIONA** — 123B parametri, coding |
| `minimax-m2.1:cloud` | MiniMax | **FUNZIONA** — Coding specializzato |
| `qwen3-coder:480b-cloud` | Qwen Coder | **FUNZIONA** — 480B parametri, coding |
| `minimax-m2:cloud` | MiniMax | **FUNZIONA** — Versione precedente |

---

## ⚠️ Modelli con limitazioni

| Modello | Stato | Note |
|---|---|---|
| `rnj-1:8b-cloud` | ⚠️ Disponibile con limitazioni | Errore max_tokens: modello supporta max 16384 token output (non 32000). Richiede config specifica. |

---

## ❌ Modelli NON disponibili (testati)

### Modelli coding richiesti (NON disponibili)

- ~~`qwen3-coder-next`~~ — NON DISPONIBILE (senza `:cloud`)
- ~~`devstral-small-2`~~ — NON DISPONIBILE (senza `:24b-cloud`)
- ~~`rnj-1`~~ — NON DISPONIBILE (senza `:8b-cloud`)
- ~~`devstral-2`~~ — NON DISPONIBILE (senza `:123b-cloud`)
- ~~`minimax-m2.1`~~ — NON DISPONIBILE (senza `:cloud`)
- ~~`qwen3-coder`~~ — NON DISPONIBILE (senza `:480b-cloud`)
- ~~`cogito-2.1`~~ — NON DISPONIBILE

### Altri modelli coding testati (NON disponibili)

- ~~`qwen3.5-coder:cloud`~~ — NON DISPONIBILE
- ~~`qwen3-coder:cloud`~~ — NON DISPONIBILE (senza `:480b`)
- ~~`qwen-coder:cloud`~~ — NON DISPONIBILE
- ~~`qwen2.5-coder:cloud`~~ — NON DISPONIBILE
- ~~`devstral:cloud`~~ — NON DISPONIBILE
- ~~`devstral-small:cloud`~~ — NON DISPONIBILE

### Modelli Mistral (tutti NON disponibili)

- ~~`mistral-medium-3.5:128b`~~ — NON DISPONIBILE
- ~~`mistral-medium:cloud`~~ — NON DISPONIBILE
- ~~`mistral-large:cloud`~~ — NON DISPONIBILE
- ~~`mistral:cloud`~~ — NON DISPONIBILE
- ~~`mistral-small:cloud`~~ — NON DISPONIBILE
- ~~`mistral-small-3.1:cloud`~~ — NON DISPONIBILE
- ~~`mistral-large-3.1:cloud`~~ — NON DISPONIBILE
- ~~`mistral-3.5:cloud`~~ — NON DISPONIBILE
- ~~`mistral-ai:cloud`~~ — NON DISPONIBILE

### Modelli Qwen general (NON disponibili)

- ~~`qwen-3.6:cloud`~~ — NON DISPONIBILE
- ~~`qwen:cloud`~~ — NON DISPONIBILE
- ~~`qwen-3.5:cloud`~~ — NON DISPONIBILE
- ~~`qwen-3-5:cloud`~~ — NON DISPONIBILE
- ~~`qwen-max`~~ — NON DISPONIBILE
- ~~`qwen-3-max:cloud`~~ — NON DISPONIBILE
- ~~`qwen3-turbo:cloud`~~ — NON DISPONIBILE

### Altri provider (NON disponibili)

- ~~`claude-sonnet-4-6`~~ — NON DISPONIBILE
- ~~`claude-opus-4-7`~~ — NON DISPONIBILE
- ~~`claude-3-5-sonnet`~~ — NON DISPONIBILE
- ~~`claude-3-opus`~~ — NON DISPONIBILE
- ~~`claude-opus-4-5`~~ — NON DISPONIBILE
- ~~`claude-sonnet-4-5`~~ — NON DISPONIBILE
- ~~`claude-haiku-4-5`~~ — NON DISPONIBILE
- ~~`grok:cloud`~~ — NON DISPONIBILE
- ~~`grok-2:cloud`~~ — NON DISPONIBILE
- ~~`llama-3.3-70b:cloud`~~ — NON DISPONIBILE
- ~~`command-r-plus:cloud`~~ — NON DISPONIBILE
- ~~`gemma-3.1:cloud`~~ — NON DISPONIBILE
- ~~`deepseek-v3:cloud`~~ — NON DISPONIBILE

---

## Riepilogo

| Categoria | Count |
|---|---|
| **Modelli funzionanti (general)** | 8 |
| **Modelli funzionanti (coding)** | 6 |
| **Modelli con limitazioni** | 1 |
| **Modelli NON disponibili** | 40+ |

**Totale modelli utilizzabili:** 14 (8 general + 6 coding)

---

## Note per l'uso

**Per coding tasks**, preferire:
1. `qwen3-coder:480b-cloud` — Massimo capacity (480B)
2. `devstral-2:123b-cloud` — High capacity (123B)
3. `qwen3-coder-next:cloud` — Ultima generazione
4. `devstral-small-2:24b-cloud` — Balanced (24B)
5. `minimax-m2.1:cloud` — Specializzato coding

**Per analisi/architettura**, preferire:
1. `opus` — Ragionamento complesso
2. `sonnet` — Bilanciato
3. `qwen3.5:cloud` — Analisi tecnica
