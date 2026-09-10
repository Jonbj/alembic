# S4 late entry — quota di movimento × P&L realizzato

Misura descrittiva per #512, generata il 2026-09-10 sui dossier gia' presenti
dal 2026-08-14 al 2026-09-08. La regola dei bucket e il campione sono stati
fissati nel commit `df6166e` prima di leggere il risultato.

La quota e' `quota_movimento_precedente_al_segnale`; le righe con
`denominatore_degenere=true` restano separate. Il P&L e' esclusivamente
`trades.net_pnl`, riletto tramite `trade_id`: non viene sostituito con MTM, con
un match FIFO o con zero quando manca.

| fascia quota | ingressi | con P&L realizzato | somma P&L | mediana P&L | win rate |
|---|---:|---:|---:|---:|---:|
| `< 0,0` | 2 | 1 | −23,06 $ | −23,06 $ | 0/1 |
| `[0,0, 0,5)` | 2 | 2 | −10,24 $ | −5,12 $ | 1/2 |
| `[0,5, 1,0)` | 20 | 12 | +12,13 $ | −1,80 $ | 5/12 |
| `>= 1,0` | 13 | 7 | **−139,19 $** | **−9,74 $** | **2/7** |
| denominatore degenere | 7 | 1 | −1,27 $ | −1,27 $ | 0/1 |
| quota mancante | 0 | 0 | — | — | — |

Copertura: 44 ingressi su 16 dossier, 23 con P&L realizzato. Sedici ingressi
storici non hanno un'identita' `trade_id` ricostruibile dai dossier pre-ledger;
gli altri casi senza P&L sono trade ancora aperti o non ancora riconciliati.
Queste assenze restano nel denominatore e impediscono di leggere il risultato
come stima definitiva o come autorizzazione a cambiare un gate.

La fascia oltre 1,0 e' negativa nel campione oggi osservabile, ma il dato resta
solo una misura shadow durante il freeze #171. Nessun ordine, soglia, peso, flag,
cooldown o parametro di strategia viene modificato.

## Riproduzione

```bash
python3 -c 'import json; from pathlib import Path; import scripts.alpha_miner_dossier as d; p=json.loads(Path("docs/evidence/dossier/2026-09-08.json").read_text()); print(json.dumps(d._distribuzione_late_entry_finestra(p.get("ingressi", []), p.get("intenti_ingresso_s4", []), d.date(2026, 9, 8)), indent=2, ensure_ascii=False))'
```

Il comando legge i dossier e interroga Postgres in sola lettura per aggiornare
`trades.net_pnl`; non riscrive alcun dossier ne' i ledger di osservazione. I
numeri sopra sono lo snapshot al 2026-09-10: una riesecuzione successiva puo'
aggiungere esiti dei trade che a quella data erano ancora aperti.
