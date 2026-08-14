# Dossier di ricerca — strategie di uscita S4

Packet documentale raccolto e verificato il **2026-08-14**.

## Baseline e perimetro

- Codice analizzato:
  `main@4eebb89c71ec31e09ec5093de56f3ac42890693f`.
- Branch della consegna:
  `research/s4-exit-feasibility-20260814`.
- Perimetro: ricerca, consolidamento e fattibilità delle strategie di uscita
  S4.
- Non sono state implementate modifiche a strategy, portfolio, scheduler,
  broker o configurazione live.

## Ordine di lettura

1. [Prompt e istruzioni per i modelli](01_PROMPT_MULTI_LLM.md)
2. [Analisi preliminare e letteratura](02_ANALISI_PRELIMINARE_LETTERATURA.md)
3. [Decisione precedente consolidata](03_DECISIONE_PRECEDENTE_CONSOLIDATA.md)
4. [Pre-registrazione D+2](04_PREREGISTRAZIONE_D2.md)
5. [Quattro risposte indipendenti](risposte/README.md)
6. [Consolidato delle strategie di uscita](consolidato_exit.md)
7. [Analisi di fattibilità tecnica aggiornata](analisi_fattibilita_exit.md)

`00_README_INVIO.md` resta il frontespizio originario del packet inviato ai
modelli. Questo file è invece l'indice della consegna completa.

## Inventario

| File | Ruolo |
|---|---|
| `00_README_INVIO.md` | Contesto e istruzioni originarie d'invio |
| `01_PROMPT_MULTI_LLM.md` | Prompt di ricerca approfondita |
| `02_ANALISI_PRELIMINARE_LETTERATURA.md` | Audit preliminare e fonti accademiche |
| `03_DECISIONE_PRECEDENTE_CONSOLIDATA.md` | Baseline decisionale precedente |
| `04_PREREGISTRAZIONE_D2.md` | Copia della pre-registrazione dell'orizzonte |
| `risposte/codex_analisi_exit_s4_2026-08-14.md` | Risposta Codex |
| `risposte/glm52_analisi_exit_s4_2026-08-14.md` | Risposta GLM-5.2 |
| `risposte/opus_analisi_exit_s4_2026-08-14.md` | Risposta Opus |
| `risposte/qwen35_analisi_exit_s4_2026-08-14.md` | Risposta Qwen 3.5 |
| `consolidato_exit.md` | Sintesi critica dei quattro report |
| `analisi_fattibilita_exit.md` | Stato runtime, tracciabilità e stime tecniche |

## Provenienza e stato

I file numerati e `risposte/README.md` provengono dal packet creato dal commit
`9388baf`. Le quattro risposte, il consolidato e la prima bozza di fattibilità
erano file non tracciati nel worktree `agent/issue-278@4ac8fec`; sono stati
trasferiti su questo branch e l'analisi di fattibilità è stata riallineata al
`main` indicato sopra.

## `economic_pnl.json`

La versione modificata e non committata di
`docs/evidence/economic_pnl.json` presente nel worktree sorgente **non è stata
copiata né aggiunta a questa consegna**. È stata consultata soltanto come
controllo contestuale: nella rigenerazione osservata la serie S4 e
`scoreboard.s4_vs_200` risultavano invariate. Il dossier non usa quel file
come evidenza confirmatoria e non dipende dalla sua versione non tracciata.

Per rendere il controllo riproducibile:

- worktree sorgente: `agent/issue-278@4ac8fec`;
- SHA-256 del file modificato:
  `d5936368d8c8077d1072af1357fdf0778ea2f085ed7e7ba947602aca1e6a3efa`;
- Git blob del file modificato:
  `ae8658b8e945aff7f02e2322b52fe738a1d63e48`;
- il sottoalbero normalizzato `scoreboard.s4_vs_200` produceva in entrambe le
  versioni SHA-256
  `d466ddbe834d9f399f2c02d56a3dd58dd488eb73e07073eeb9205bece75b17a6`.

Comandi usati nel worktree sorgente:

```bash
jq -S -c '{s4:.scoreboard.s4_vs_200}' docs/evidence/economic_pnl.json | sha256sum
git show HEAD:docs/evidence/economic_pnl.json | jq -S -c '{s4:.scoreboard.s4_vs_200}' | sha256sum
```

## Limiti

- Le issue GitHub sono informazioni vive: stato e ownership vanno ricontrollati
  prima di qualsiasi implementazione.
- Le stime nella fattibilità sono giorni-persona di engineering, non durata del
  forward sample.
- Le circa 213 sedute citate dalla pre-registrazione riguardano il gate IC; la
  numerosità del paired exit test deve essere calcolata separatamente.
