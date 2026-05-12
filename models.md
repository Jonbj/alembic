# Modelli disponibili e testati

**Ultimo aggiornamento:** 2026-05-06  
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
| `ministral-3:14b-cloud` | Ministral | Cloud — Testato OK |
| `nemotron-3-super:cloud` | NVIDIA | Cloud — Testato OK |
| `gemini-3-flash-preview:cloud` | Gemini | Cloud — Testato OK |

### Modelli Specifici per Coding ⭐

| Modello | Tipo | Note |
|---|---|---|
| `qwen3-coder-next:cloud` | Qwen Coder | **FUNZIONA** — Coding specializzato |
| `devstral-2:123b-cloud` | Devstral | **FUNZIONA** — 123B parametri, coding |
| `minimax-m2.7:cloud` | MiniMax | **FUNZIONA** — Coding, agentic workflows |
| `qwen3-coder:480b-cloud` | Qwen Coder | **FUNZIONA** — 480B parametri, coding |
| `minimax-m2:cloud` | MiniMax | **FUNZIONA** — Versione precedente |

---

---

## Riepilogo

| Categoria | Count |
|---|---|
| **Modelli funzionanti (general)** | 11 |
| **Modelli funzionanti (coding)** | 5 |

**Totale modelli utilizzabili:** 16 (11 general + 5 coding)

---

## Note per l'uso

**Per coding tasks**, preferire:
1. `qwen3-coder:480b-cloud` — Massimo capacity (480B)
2. `devstral-2:123b-cloud` — High capacity (123B)
3. `qwen3-coder-next:cloud` — Ultima generazione
4. `minimax-m2.7:cloud` — Specializzato coding

**Per analisi/architettura**, preferire:
1. `opus` — Ragionamento complesso
2. `sonnet` — Bilanciato
3. `qwen3.5:cloud` — Analisi tecnica
