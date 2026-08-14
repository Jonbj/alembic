# S4 — Analisi dell'orizzonte economico

**Modello:** Qwen3.5 (397B, via Claude Code)  
**Data risposta:** 2026-08-14  
**Issue di riferimento:** #242

---

## Analisi preliminare

Prima di rispondere alle domande, devo essere esplicito su cosa vedo nei dati:

1. **La dissonanza centrale:** S4 ha un P&L realizzato positivo (+209$) ma un IC ≈ 0. Questo non è un paradosso statistico — è il segnale che **S4 non sta catturando alpha direzionale**, ma sta guadagnando su qualcos'altro (timing intraday, mean reversion a brevissimo termine, o semplicemente fortuna su n piccolo).

2. **Il meccanismo di uscita è il vero driver:** Il 67% delle uscite (6 su 9) nella finestra analizzata avviene a 1h45 o 4h15 esatte. Questo non è un orizzonte economico — è un orizzonte *artificiale* dettato dalla cadenza delle news e dal `max_signal_age_hours`. S4 non "decide" quando uscire; viene *forzato* a uscire quando la fonte smette di pubblicare o quando scatta il TTL.

3. **L'IC è misurato sull'orizzonte sbagliato, ma questo è il meno dei problemi:** Anche se rimisurassimo l'IC a 1h/4h, il problema di fondo resta: **il segnale LLM non sta predendo il movimento**. La news arriva dopo che il movimento è già avvenuto (§3.4: 70-84% del movimento già priced-in al primo segnale). Un IC positivo a brevissimo termine sarebbe probabilmente noise o microstruttura, non alpha informativo.

4. **La sovrapposizione con S1 è il vero problema strategico:** 21 intenti S4 su 30 bloccati dal guard anti-pyramiding perché S1 già deteneva il titolo. Questo non è un "overlap" — è S4 che cerca di comprare ciò che S1 ha già comprato, ma *dopo*. Se S4 fosse una sleeve indipendente con alpha proprio, vedrebbe titoli che S1 non vede.

---

## Risposte alle domande della Sezione 7

```
SCELTA:            C (shadow) — S4 non ha un orizzonte economico proprio; quello "effettivo" (4h15) è un artefatto della cadenza di pubblicazione delle news, non una decisione di investimento. Non è A perché l'intraday richiederebbe alpha intraday che la news editoriale non può dare (arriva tardi). Non è B perché forzerebbe un orizzonte multi-day su un segnale che non lo regge (IC 3g = +0.0126, rumore). Shadow preserva la serie storica, azzera i costi (99$ su 209$ di lordo), e libera il 10% per una sleeve con alpha vero.

CONFIDENZA:        media — alta sulla direzione (C), media sui tempi. Alta perché: (1) il meccanismo di uscita "non deciso" è strutturale e non si risolve con tweak; (2) l'IC su dati sporchi non può essere base per decisioni; (3) la sovrapposizione S1 è sintomo di mancanza di alpha indipendente. Media perché: n=38 sull'IC è davvero piccolo, e le correzioni al ticker resolver (§3.6) potrebbero — in linea di principio — rivelare un segnale più pulito. Ma la latenza della news editoriale resta un vincolo fisico, non misuratorio.

CRITERIO DI FALSIFICAZIONE:  Se, dopo il deploy delle correzioni al ticker resolver e alla qualità del dato (§3.6), su n≥73 giorni (criterio pre-registrato #179) la media degli IC ensemble a 1g/3g/5g fosse ≥0.05 con t-stat ≥2, allora S4 ha alpha misurabile e merita di uscire da shadow. In alternativa: se un test su orizzonte intraday (1h/4h/close) mostrasse IC ≥0.08 con t-stat ≥2 su n≥40 giorni, S4 intraday sarebbe giustificato. Entrambi i criteri sono calcolabili sui dati che già abbiamo (s4_ic.json + forward returns da Alpaca).

RIMISURA DELL'IC:  Tre orizzonti distinti, tutti cross-sectional Spearman:
  (1) Intraday: entry→close della stessa seduta (per S4 intraday)
  (2) 1 giorno: close→close successivo (orizzonte minimo per alpha direzionale)
  (3) 4 giorni: close→close+4 (orizzonte "sweet spot" per news-driven)
  Metodo: solo ensemble (no fallback), solo alta confidenza (≥0.30), winsorizzato a 2σ per outlier.
  n minimo: 73 giorni (criterio #179), ma con power analysis: per rilevare IC=0.05 con power=0.8 serve n≈160; con n=73 il minimo rilevabile è ~0.10. Se a n=73 l'IC è <0.10, il test è inconclusivo e serve più tempo.

L'EVIDENZA BASTA?  No — manca la misura dell'IC su dati "puliti" (dopo le correzioni §3.6). Ma: la latenza della news editoriale (82% del movimento già avvenuto) è un vincolo fisico che non si risolve con dati puliti. La misura che manca è: forward returns a 1h/4h su segnali con ticker corretto. Tempo per raccoglierla: 40 sedute (già in corso, deroga fino al 28/09). Tuttavia, la mia raccomandazione C non attende questa misura: shadow è reversibile, i costi sono reali (99$), e l'opportunità costata (10% di NAV fermo) è giustificata solo se c'è alpha — che oggi non vediamo.

SEQUENZA DI DEPLOY:  1) Shadow immediato (stop execution, continua logging segnali + IC). 2) Deploy correzioni ticker resolver e qualità dato (§3.6) in shadow. 3) Raccolta 40 seduti di IC pulito a 1h/4h/1g. 4) A n≥40, decisione: se IC ≥ soglia → riattivazione con orizzonte esplicito (A o B); se no → chiusura definitiva. Motivo: shadow è reversibile e azzera il danno economico; le correzioni vanno testate in shadow per non contaminare la serie; 40 sedute è il minimo per una misura stabilizzata ma non il massimo (73) per non prolungare l'incertezza.

COSA HO IGNORATO:  Il P&L realizzato +209$ di S4 — l'ho ignorato come base decisionale perché è avversamente selezionato (S1 compensa in MTM, non in realizzato) e perché su n=81 trade con win rate 53% non è statisticamente distinguibile da fortuna. Il controfattuale "all'apertura" (§3.3) — l'ho ignorato perché usa informazione futura, come il documento stesso avverte. La t-stat di -4.96 sull'ora 14 UTC (§6.7) — l'ho ignorata su esplicita avvertenza del documento.

DISSENSO:  (1) La §3.2 dice che "la finestra di 5 giorni è la settimana peggiore" — vero, ma su n=9 non si può inferire che le altre settimane siano "rappresentative". S4 ha avuto 4 settimane positive e 1 negativa: è un campione troppo piccolo per dire che il difetto meccanico è "reale e permanente" solo perché si è manifestato nella settimana negativa. Il difetto è reale, ma la sua dimensione economica potrebbe essere sovrastimata tanto nella settimana negativa quanto sottostimata in quelle positive. (2) La §5.5 dice che ogni cambiamento crea discontinuità — vero, ma shadow non è un cambiamento di *parametro*, è un cambiamento di *regime*. La serie IC resta confrontabile (shadow continua a produrre segnali), mentre il P&L si interrompe. Questo è un punto che il documento tratta come più problematico di quanto sia. (3) La §3.1 riporta una "tenuta mediana" di 1h45 per S4 — ma 6 uscite su 9 sono a 1h45 o 4h15 *esatte*. Questo non è "tenuta", è scadenza. La mediana è fuorviante perché suggerisce una distribuzione quando c'è un artefatto deterministico.
```

---

## Sintesi per l'operatore

**Raccomandazione:** Passare S4 in shadow immediatamente, deployare le correzioni alla qualità del dato in shadow, raccogliere 40 sedute di IC pulito a orizzonti multipli (1h/4h/1g), e rivalutare a n≥40.

**Perché non A (intraday):** La news editoriale arriva dopo che il movimento è avvenuto (70-84% priced-in). Non c'è alpha intraday da catturare senza fonti event-driven a bassa latenza (filing, earnings, transcript) — che richiedono infrastruttura nuova.

**Perché non B (1-3 giorni):** L'IC a 3 giorni è +0.0126 (rumore). Forzare un orizzonte multi-day su un segnale che non lo regge significa impegnare capitale per 1-3 giorni su alpha nullo, con rischio di sovrapposizione con S1.

**Perché C (shadow):** È reversibile, azzera i costi (99$ su 209$ di lordo = 32% di alpha eroso), libera il 10% di NAV, e preserva la serie storica per decisioni future basate su dati puliti.

**Tempo:** 40 sedute (deroga già concessa fino al 28/09). A quel punto, con n≥40 e dati puliti, la decisione di riattivazione o chiusura definitiva sarà basata su evidenza, non su rumore.
