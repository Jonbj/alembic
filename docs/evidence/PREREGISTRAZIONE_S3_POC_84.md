# Pre-registrazione — POC di allineamento al design S3 (issue #84)

Scritta il **2026-09-17**, prima di qualunque run su dati reali e prima che un
dataset PIT qualificato esista. Il POC è **offline**: non promuove S3 a shadow,
paper o live, e per mandato esplicito della issue un PASS produce soltanto un
decision brief.

Issue: [#84](https://github.com/Jonbj/alembic/issues/84) · Decisione a monte: #55 ·
Parte di #21.

## 0. Cosa fissa questo documento e cosa no

Le soglie, gli split, i costi, il conteggio dei trial e le regole di esito sono
**macchina-leggibili** e vivono in `docs/evidence/S3_POC_MANIFEST_84.yaml`. Questo
documento non li duplica: li **sigilla** registrandone lo sha256, dichiara le
ipotesi in prosa e fissa l'ordine delle operazioni.

- Manifest sigillato: `docs/evidence/S3_POC_MANIFEST_84.yaml`
- sha256 al momento del sigillo: `3946bf4c47bcbc1926dd11be6faea23cae454dc100c19790016fd1dd217164ab`
- Codice del POC: `src/analysis/s3_poc/` (nessun contatto con registry, ordini,
  shadow, paper o live)

Ogni artefatto prodotto dal runner (`run_poc`) cita il proprio path di manifest e
il proprio sha256. **Un artefatto il cui sha256 non coincide con quello qui sopra
non è stato prodotto sotto questa pre-registrazione** e va trattato come
esplorativo, non come evidenza.

## 1. Le due ipotesi, in una frase ciascuna

- **H_A (design originale).** Il momentum cross-sectional 12-1 *corretto per beta*,
  top decile long-only con sizing inverse-vol, ha uno Sharpe netto OOS sopra 0,30
  dopo costi, e migliora il portafoglio S1+cassa sostituendo 10 punti di cassa.
- **H_B (comparatore).** Lo stesso portafoglio costruito sul momentum 12-1 *totale*,
  senza correzione per beta.

**B è comparatore, non veto.** La correzione beta sopravvive solo se aggiunge
valore materiale; il fallimento di B non respinge un A genuinamente riuscito.

## 2. La nulla, e cosa il campione può davvero rilevare

La nulla è che il decile alto non abbia rendimento in eccesso netto rispetto ai
costi: Sharpe netto OOS = 0. Il campione di sviluppo va dal 1998 al 2022, con
walk-forward 60/12/12: **20 finestre OOS non sovrapposte** da 12 mesi, dal 2003 al
2022 (i primi 60 mesi sono in-sample per la prima finestra).

Con 20 finestre annuali, ciò che il campione può separare è uno Sharpe
persistente dell'ordine di 0,3–0,5; **non** può distinguere 0,05 da 0,15. Un
risultato dentro quella banda è indistinguibile dal rumore per costruzione, non
"un piccolo edge": va letto come `INSUFFICIENT_N`, non come esito.

Lo Sharpe OOS storico vicino a 0,148 è un artefatto esplorativo su un portafoglio
diverso e su un universo survivor: **non è né un PASS corrente né una confutazione
valida della variante A**, e non entra in questa pre-registrazione se non come
motivo per cui il POC esiste.

## 3. L'ordine delle operazioni — vincolante

1. **Gate dati.** Nessun run decision-grade senza dataset PIT qualificato
   (`docs/RESEARCH_S3_PIT_DATA_FEASIBILITY_2026-07-21.md`, esito provvisorio
   NO-GO al 2026-07-21). Il runner rifiuta dati reali non qualificati:
   `require_qualified_or_synthetic`.
2. **Sviluppo e walk-forward** sul solo campione 1998-2022. Il codice del POC può
   cambiare in questa fase; il manifest no. Ogni modifica del manifest in questa
   fase invalida il sigillo e richiede un nuovo sha256 registrato qui sotto, in
   §6, con la data e il motivo.
3. **Review indipendente** su uso causale dei dati, membership PIT, delisting,
   isolamento delle finestre, fedeltà A/B, costi e conteggio dei trial. Registrata
   in `docs/evidence/S3_POC_HOLDOUT_SIGNOFF_84.md`.
4. **Holdout 2023-2025: una volta sola**, dopo il sign-off. Il runner rifiuta di
   aprirlo senza sign-off registrato. Qualunque modifica dell'ipotesi dopo questo
   punto **brucia il holdout** per l'ipotesi modificata.
5. **Decision brief.** Un PASS si ferma qui. Hardening, shadow, paper, wiring del
   broker e allocazione richiedono issue figlie e approvazione umana esplicita.

## 4. Il difetto che poteva invalidare tutto, e perché è registrato qui

Fino al 2026-09-17 il motore comprava all'open della seduta di esecuzione ma
**liquidava le posizioni uscite dal decile al close della stessa seduta**
(`engine.py`, risoluzione dei fill costruita sui soli nomi del piano). Il manifest
congela `execution: next_session_open` con il close come solo fallback: comprare
all'open e vendere al close è una deviazione sistematica dalla regola registrata,
su **ogni** rotazione mensile — cioè su gran parte del book di una manica momentum.

Non è look-ahead e, essendo simmetrica fra A e B, non distorce il confronto; ma
alimenta i gate standalone e il test combinato, che sono la metrica decisionale.

È stato corretto **prima di qualunque run**, quindi non interrompe nessuna serie
pubblicata e non richiede un'annotazione di discontinuità nel charter. È
registrato qui perché la pre-registrazione vale solo se lo strumento esegue la
regola registrata: scoprire lo stesso difetto *dopo* il campione di sviluppo
avrebbe richiesto di rieseguirlo.

## 4-bis. Limitazioni dichiarate prima del run

Dichiarate ora perché siano leggibili accanto al risultato, non scoperte dopo:

- **La mediana di volatilità che separa i regimi high/low è calcolata sull'intero
  periodo valutato** (`evaluation.py`), non su una finestra trailing. È
  un'etichettatura dei regimi che guarda il campione intero: simmetrica fra A e B,
  ma non causale. Il manifest congela `vol_split: "median"` senza qualificarla, e
  qui resta così — cambiarla ora sarebbe modificare una soglia congelata. Se il
  gate dei regimi risulta decisivo per l'esito, quel fatto va scritto nel decision
  brief e la definizione va rifatta trailing **prima** di qualunque passo
  successivo.
- **Il rendimento della cassa sostituita nel test combinato è fissato a zero**
  (`cash_return: 0.0`). È una semplificazione conservativa verso S3 in regime di
  tassi alti: sopravvaluta il contributo della manica rispetto a tenere cassa
  remunerata. Va letta come tale, non ignorata.
- **I costi vengono dal tier_d di produzione** (spread 20 bps), cioè il default
  conservativo per simboli non mappati. Lo scenario 2x è obbligatorio proprio
  perché questa stima non è osservata sul periodo 1998-2022.

## 5. Cosa non si farà

- Non si sceglie la variante dopo aver visto il holdout.
- Non si aggiungono varianti di segnale (FF3 residual momentum, filtri di momentum
  assoluto, neutralizzazione settoriale, gamba corta): non sono nel manifest.
- Non si rilassano i gate per S3. Il registro dei trial (`n_trials_for_dsr: 6`)
  conta i trial davvero esplorati, comprese le perturbazioni storiche.
- Non si sostituisce il dataset PIT con la lista survivor corrente. Se nessun
  fornitore chiude tutte le condizioni entro il tetto di €1.000, l'esito è un
  **NO-GO infrastrutturale**, non un run su dati peggiori.
- Le allocazioni 5% e 15% restano diagnostiche: non diventano una seconda ricerca.

## 6. Registro delle rotture del sigillo

Nessuna. Ogni modifica del manifest dopo il 2026-09-17 va aggiunta qui con data,
nuovo sha256, motivo e impatto sugli artefatti già prodotti.

| Data | Nuovo sha256 | Motivo | Artefatti invalidati |
|------|--------------|--------|----------------------|
| —    | —            | —      | —                    |
