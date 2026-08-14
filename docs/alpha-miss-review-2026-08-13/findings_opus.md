# Come migliorare il report alpha-miss di Alembic

Ho letto tutto: lo script, i due report, il dossier deterministico (`scripts/alpha_miner_dossier.py` + `docs/evidence/dossier/*.json`), i 38 findings, le 9 righe del panel di mercato, la carta e `trading.yaml`.

Prima la diagnosi, poi le cinque aree.

---

## Diagnosi: il report è ottimo come cronaca, debole come esperimento

I due report che ho letto sono di qualità alta — la decomposizione gap/intraday del 08-12 e il rifiuto di riportare F-030 quando il denominatore degenera sono lavoro serio. Il problema non è la qualità del singolo giorno: sono tre difetti strutturali.

1. **Il report misura il pipeline, non l'alpha.** La tassonomia dei miss (NO_NEWS / THIN_NEUTRAL / …) descrive *dove si è rotta la catena*, non *se c'era qualcosa da prendere*. Il 08-12 lo dimostra: 99% mediano del movimento nel gap → i miss sono contabilizzati su movimenti mai stati accessibili. Il costo del miss di ORCL passa da $117,95 a $6,82 a seconda di quale numero usi, e questa distinzione è stata inventata dalla sessione quel giorno, non è nel protocollo.

2. **La ricorrenza è un conteggio senza denominatore.** "Sesta giornata del pattern" (F-008) su quante giornate in cui il pattern *poteva* manifestarsi? Non lo sappiamo. La carta fa scattare la roadmap su ≥10 giorni distinti o ≥15 occorrenze non stimate: con 38 findings quasi tutti `aperto` e quasi tutti a costo null, al giorno 40 ne attraverseranno la soglia una ventina, tutti pari merito. **Il meccanismo di selezione fallirà per eccesso di ammissioni, non per difetto.**

3. **Le due domande di uscita pre-registrate non vengono mai calcolate.** La carta definisce il **P&L economico** (§"Definizione") come metrica di entrambe le domande, e lo dichiara esplicitamente diverso dal realizzato. Il dossier e i report riportano `realizzato`, `mtm`, `s1_realizzato`, `s4_realizzato` — mai il P&L economico cumulato dal 08-03. Al 28/09 qualcuno dovrà ricostruirlo all'indietro. Stessa cosa per "NO_NEWS dominante in ≥60% dei giorni": calcolabile, mai tracciato.

Tutto il resto discende da qui.

---

## 1) Metriche e sezioni che mancano

**a. Alpha accessibile — il denominatore che manca ovunque.**
Per ogni mover, tre numeri invece di uno: `movimento_totale` (close/close_prec), `movimento_nel_gap`, `movimento_residuo_al_primo_segnale` (dal prezzo all'ora del primo segnale scorato alla chiusura). Il costo di un miss si stima **solo sul terzo**. Questo:
- rende strutturale ciò che il 08-12 ha fatto a mano;
- rende automatico il "costo 0 verificato" per i mover al ribasso su libro long-only (il 08-11 l'ha scritto in prosa sei volte);
- e soprattutto produce l'aggregato che oggi non esiste: **`alpha_accessibile_del_giorno`** = somma su tutti i mover della porzione catturabile × size tipica. Senza questo, "8 catturati su 11" e "−35 $ sulle tre decisioni" non sono confrontabili con niente.

**b. Rendimento residuo, non assoluto.** La soglia mover è su `|return| ≥ 3%` assoluto. Il 08-12 nove mover su undici sono lo stesso trade (memoria/semi): non sono nove eventi, è uno. Calcola il residuo vs il settore (avete già XLK/SOXX/XLF/XLE/XLV/SPY in watchlist come proxy gratuiti) e classifica i mover per **return idiosincratico**. È quello che la news può prevedere; il beta di settore no. Sospetto che questo cambi materialmente l'insieme dei miss e faccia sparire metà dei "NO_NEWS" tematici.

**c. IC giornaliero sull'intera sezione trasversale.** Oggi si guarda solo la coda |ret|≥3%: è selezione sul campione. Avete `sentiment_signals` su ~45 simboli/giorno e i rendimenti su tutti e 96. Lo Spearman fra (score max del giorno) e (rendimento dal primo segnale alla chiusura) costa niente e risponde alla domanda di uscita n.1 molto meglio del conteggio NO_NEWS. Aggiungi le versioni condizionate: **IC sui segnali da articolo ticker-specifico vs IC sui fan-out** (converte F-012 da osservazione strutturale a misura), e IC per fascia di `ensemble_std` (converte F-037).

**d. La metà simmetrica mancante: i falsi positivi.** Il report si chiama alpha-*miss* e guarda solo ciò che non è stato comprato. Ma il 08-12 le tre decisioni attive perdono soldi su tre titoli chiusi in verde. Serve una sezione fissa: ogni BUY del giorno con score d'ingresso e rendimento forward a +1h / EOD / +1g / +3g. Aggregata sulla finestra, la regressione `rendimento_forward ~ score` è **la** risposta a "il punteggio predice", e non richiede alcuna deroga.

**e. P&L della decisione, separato dal P&L del libro.** Il 08-12 lo dice benissimo: +271 $ di MTM tutti da posizioni tenute passivamente da 2-4 settimane, −35 $ dalle tre decisioni prese quel giorno. Questa scomposizione va resa una serie: `pnl_decisioni_del_giorno` = Σ(ingressi: close−entry)·qty + Σ(uscite: −drift_post_uscita). Cumulata su 40 giorni è l'unica misura di quanto il motore aggiunga rispetto al non fare nulla.

**f. Modello nullo.** −35 $ su tre ingressi non è leggibile senza un termine di paragone. Tre benchmark banali da calcolare a posteriori: (i) stessa size, stesso orario, simbolo estratto a caso dalla watchlist; (ii) equal-weight buy&hold della watchlist; (iii) ingresso all'apertura sugli stessi tre nomi. **Questo serve in particolare per F-030(b)**: la mediana di `entry_percentile` a 0,535 e gli ingressi a 0,77/0,71/0,92 sono presentati come "compriamo sul massimo", ma una strategia che compra su news positiva intraday *avrà per costruzione* un percentile alto sui titoli che chiudono in rialzo. Il null model corretto è: percentile d'ingresso *condizionato al fatto che il titolo chiude +X%*. Senza, F-030(b) è sovradichiarato e al 28/09 rischia di portare in roadmap un fenomeno inesistente.

**g. Sufficienza statistica, riportata ogni giorno.** La dispersione si sta comprimendo (4,40 → 1,54%). La carta prevede come esito legittimo "estendere la finestra". Riporta ogni giorno i gradi di libertà accumulati: quanti mover con alpha accessibile > 0, quanti ingressi S4, quale precisione avrà la stima del P&L economico S4 al giorno 40 al ritmo attuale. Se al giorno 20 è già chiaro che ±$200 non sarà distinguibile dal rumore, lo si sa a metà percorso e non alla scadenza.

**h. Copertura *utile*, non copertura.** `watchlist_zero_news` conta righe in `news_log`, ma F-020 dice che il 40% delle righe `org_lookup` va a tre banche che non c'entrano, e F-012 che metà delle righe scorate viene da fan-out. Quindi **sia il numeratore sia il denominatore di F-001 sono contaminati**. La metrica giusta è una sola: `copertura_specifica` = simboli con ≥1 articolo di cui il ticker è *il soggetto* (cashtag o match nel titolo). F-001, F-012 e F-020 sono lo stesso fenomeno misurato tre volte con tre metriche diverse; una metrica sola li unifica e alla scadenza produce un'evidenza invece di tre mezze evidenze.

---

## 2) Modifiche al prompt

**a. La modifica più importante: obbligare al denominatore e alla falsificazione.**
Per ogni finding toccato, il prompt deve richiedere due campi:
- *cosa avrebbero mostrato i dati di oggi se il finding fosse falso*;
- se i dati lo mostrano, registrare una **non-occorrenza**, non tacere.

Oggi il report è a forma di conferma: ogni giorno riconferma F-001, F-012, F-020, F-030 e nessuno può essere ritirato. Con `giorni_esposti` accanto a `occorrenze`, "sesta giornata del pattern" diventa "6 su 9 giornate in cui era osservabile" — che è un'affermazione.

**b. Codifica lo stimatore di costo, non lasciarlo alla sessione.** Il prompt dice "usa ~2% del NAV × il movimento". Il 08-12 ha correttamente usato la porzione catturabile. Risultato: `costo_cumulato_usd` somma stime prodotte da formule diverse in giorni diversi — F-001 ha già $1.259,85 (sopra la soglia congetturale di $1.000) al giorno 8 su 40, quasi tutti dallo stimatore vecchio. **La somma non è confrontabile con la soglia che dovrebbe attraversare.** Sposta il calcolo nel dossier (deterministico, versionato), aggiungi `stima_versione` a ogni occorrenza, e lascia alla sessione solo il giudizio su *quale* stimatore si applica. Non tocca le occorrenze già scritte, quindi non viola l'append-only.

**c. Elimina il residuo pre-dossier.** Il prompt chiede ancora "definisci tu una soglia ragionevole, motiva la scelta": il dossier la fissa a 0,03 e le sessioni la ri-motivano ogni giorno in modo diverso (1,27σ il 08-12, 2σ il 08-11). Sono token spesi per produrre incoerenza. Stessa cosa per la FASE 1 con l'esempio di codice Alpaca: è morta, il dossier fa già il lavoro.

**d. Taglia la tabella dei 96 rendimenti dal report.** Sono ~100 righe su 326 che duplicano il dossier e che nessuno legge. L'attenzione dell'operatore è la risorsa scarsa. Metti solo i mover + i simboli con posizione, e rimanda al JSON per il resto.

**e. Sezione obbligatoria "Stato delle due domande di uscita".** Cinque righe fisse: contributo di oggi al P&L economico di S4 e di S1, cumulato dal 08-03, frazione di giornate con NO_NEWS dominante, confronto S1 vs SPY. Se il criterio della carta è pre-registrato, va segnato ogni giorno, non ricostruito alla fine.

**f. Passo avversariale prima di scrivere.** "Elenca le due spiegazioni alternative del pattern dominante di oggi che hai scartato, e perché." Il 08-12 lo ha fatto spontaneamente (ha rifiutato F-030 perché il denominatore degenerava): istituzionalizzalo invece di sperarci.

**g. Per ogni finding di tipo `difetto`, richiedi la "prova decisiva".** Non un fix — la carta lo vieta — ma: la posizione nel codice + **il più economico esperimento read-only che lo confermerebbe o smentirebbe**. Al 28/09 la roadmap pesata diventa una lista di esperimenti con un costo noto, non una lista di opinioni.

**h. Vincola il report a essere leggibile solo da §1 e §7.** Dichiara nel prompt che l'operatore legge quelle due sezioni: l'executive summary deve reggersi da solo e §7 deve avere ogni numero con unità e orizzonte.

---

## 3) Dati aggiuntivi e cross-analisi

In ordine di rapporto valore/sforzo:

**a. Barre intraday a 5 minuti sui mover e sui simboli con segnale (Alpaca, incluse nell'abbonamento).** Sblocca da sola metà delle metriche sopra: prezzo all'ora esatta del primo segnale, prezzo all'ora dell'ordine, MFE/MAE dopo l'ingresso, `entry_percentile` calcolato sul percorso reale invece che sul range giornaliero. Oggi `entry_percentile` sul range daily è una proxy grezza su cui poggia F-030(b), cioè uno dei findings più costosi del ledger.

**b. Le quattro marche temporali della notizia: `published_at → fetched_at → scored_at → decisione`.** F-019 ha misurato la latenza una volta (~1h50m mediana). Va decomposta e incrociata col percorso di prezzo: **quanta parte del movimento avviene in ciascuno dei quattro stadi**. È la cross-analisi più decisiva che avete a disposizione, perché discrimina fra due conclusioni radicalmente diverse: se il movimento è già avvenuto *prima* di `published_at`, nessun intervento di ingegneria lo recupera e la domanda di uscita n.1 è risolta a favore del pivot verso i vettori strutturati Tier A; se avviene fra `published_at` e `scored_at`, è latenza e si aggiusta.

**c. Calendario societario (earnings, guidance, ex-div) e tipizzazione dell'evento.** Ogni mover etichettato `earnings | guidance | analyst | M&A | macro | idiosincratico`, con incrocio causa-di-miss × tipo-di-evento. Se i miss si concentrano sui gap post-earnings, il problema non è la copertura news: è che state cercando alpha in una classe di eventi strutturalmente non accessibile a un motore RTH — che è un'affermazione molto più forte di "51/96 simboli senza copertura".

**d. Libro ombra controfattuale, read-only.** Ri-esegui la logica di selezione S4 sui segnali *effettivi* del giorno con gate a 0,20 / 0,30 / 0,40, e con i fan-out esclusi. Registra il P&L teorico. È **misurazione, non taratura** — non tocca nulla in produzione — quindi passa il test della carta senza deroga. Su 40 giorni dà la risposta a "il gate è il collo di bottiglia" con una curva, mentre F-009 oggi la dà con quattro aneddoti e per giunta contaminati dalla discontinuità #191 già annotata nella carta.

**e. Follow-up a T+1 / T+3 / T+5.** Il dossier del giorno D deve **riaprire** ingressi, uscite e miss di D−1, D−3, D−5 e riempirne il rendimento forward. Oggi tutto è troncato a EOD, mentre S4 tiene 4-20h e S1 settimane: giudicare un ingresso sul MTM di fine giornata è un disallineamento di orizzonte che spinge sistematicamente verso la conclusione "entriamo sul massimo" (che intraday è in buona parte mean-reversion). Con i forward returns quella conclusione diventa falsificabile — e il costo dei miss diventa onesto: un mover che continua a correre è un miss diverso da uno che ritraccia il giorno dopo.

**f. Distribuzione dei punteggi su tutta la watchlist, non solo sui mover.** Quanti simboli hanno ricevuto *un* punteggio (copertura dello scorer, distinta dalla copertura news), forma della distribuzione, tasso di fallback per modello, `ensemble_std`. Se la distribuzione è degenere attorno a zero, il gate a 0,30 non è una soglia: è un interruttore.

---

## 4) Struttura di findings e ledger

**a. Tre pannelli tidy invece di un pannello e 40 markdown.** Oggi esiste solo `market_daily.jsonl` (una riga/giorno). Aggiungi:
- **panel decisioni**: una riga per ingresso/uscita, con score, ora, percentile, forward returns riempiti progressivamente;
- **panel segnali**: una riga per (giorno, simbolo) con score, copertura, specificità dell'articolo, latenza, rendimento forward.

Al giorno 40 qualsiasi domanda diventa un groupby su tre file, non la rilettura di 40 report da parte di un LLM. È la stessa logica che ha motivato il dossier (#174), applicata al longitudinale invece che al giornaliero.

**b. Campi mancanti su `findings.json`:**
- `giorni_esposti` accanto a `occorrenze` — vedi il punto sul denominatore;
- `classe`: `alpha | esecuzione | strumentazione | cosmetico`;
- **`contamina_evidenza: true/false`** — il campo più importante da aggiungere;
- `meccanismo` (file:riga) e `prova_decisiva` (l'esperimento);
- `strategia_impattata` (S1 / S4 / pipeline / telemetria);
- `stima_versione` sull'occorrenza.

**c. `contamina_evidenza` merita un canale separato e immediato.** F-011 (`signal_id` NULL su 505/508 righe) rompe la tracciabilità segnale→ordine, cioè l'ossatura di ogni controfattuale che questi report scrivono. F-027 (i log dei container non sopravvivono al redeploy), F-028 (i test scrivono nel DB di produzione), F-002 (11 posizioni senza attribuzione di strategia — che confligge direttamente con la domanda di uscita n.2), F-006 (il segno perso in `execution_decisions`, che è esattamente il campo su cui verrà falsificata la domanda n.1). Questi **passano il test di esenzione della carta** — "se non lo correggo, l'evidenza che raccolgo è sbagliata" — e vanno decisi dall'operatore subito, non pesati al giorno 40 insieme agli alpha miss. Oggi stanno nello stesso mucchio e verranno ordinati per dollari, che non hanno. Ogni giorno di ritardo è finestra bruciata.

**d. Stati oltre `aperto`.** Servono `confermato`, `smentito`, `strumentale`, `fuso_in:F-NNN`. Con 38 findings tutti aperti all'ottavo giorno su quaranta, la proiezione lineare è ~100 record: il ledger diventa illeggibile molto prima della scadenza. La regola "nel dubbio aggancia" è giusta ma senza un meccanismo di ritiro produce solo accumulo.

**e. `SYNTHESIS.md` rigenerato ogni giorno, deterministicamente, dai ledger.** Giorni trascorsi/rimanenti, per ogni finding la **distanza dalla sua soglia** e la proiezione al giorno 40, stato delle due domande di uscita, i cinque findings con la proiezione più alta, i findings che oggi hanno registrato una non-occorrenza. È un rendering, non un'analisi: nessun LLM, nessun rischio di deriva. Diventa l'unica cosa che l'operatore deve leggere quotidianamente, e rende visibile il *cumulato* che oggi non guarda nessuno.

**f. Un allarme, non un report.** Aggiungi la sezione "Cosa è cambiato dal cumulato" e mandala su Telegram al posto dei primi 3800 caratteri di prosa: findings che hanno attraversato una soglia oggi, findings ritirati, movimento delle due domande di uscita, P&L cumulato delle decisioni. Tre numeri, non tre schermate.

---

## 5) Altre idee per l'actionability

- **Pre-registra al controllo di metà periodo (28/08) i cinque findings attesi in cima al giorno 40**, e confrontali alla scadenza. Costa dieci minuti ed è l'unica difesa contro il senno di poi — coerente con lo spirito della carta, che è nata proprio "per togliere a noi stessi la possibilità di razionalizzare a posteriori".
- **Meta-report settimanale del venerdì** (non giornaliero): consolida, fonde i duplicati, verifica l'integrità dei pannelli, ricalcola i cumulati, ritira i findings smentiti. I report giornalieri stanno derivando verso la ri-narrazione della stessa evidenza; la sintesi va fatta a cadenza diversa dall'osservazione.
- **Trappola statistica da segnalare adesso:** `aggregati.per_ora_ingresso` produce un `t_stat` su sette bucket orari da tutto lo storico. Sono sette confronti simultanei su un campione data-mined: prima o poi uno passerà 2σ per caso, e finirà in un report come "gli ingressi delle 17:00 sono strutturalmente peggiori". O applichi una correzione per molteplicità, o marca esplicitamente quel blocco come **descrittivo, non inferenziale**, nel dossier stesso — dove la sessione lo legge.
- **Ancora sulla soglia dei costi:** con lo stimatore attuale F-001 è già a $1.259 su una soglia di $1.000 all'ottavo giorno su quaranta. O la soglia è mal calibrata, o lo stimatore è gonfio (io propendo per il secondo: usa il movimento pieno invece della porzione accessibile). Vale la pena ricalibrare *adesso*, dichiarandolo, invece di scoprire al 28/09 che tutti i findings congetturali hanno attraversato la soglia e la roadmap pesata non ordina niente.

---

**Se ne fai solo cinque, questi:** (1) alpha accessibile come denominatore, con lo stimatore di costo spostato nel dossier; (2) `giorni_esposti` + non-occorrenze, per dare un denominatore alla ricorrenza; (3) P&L economico e stato delle due domande di uscita calcolati e riportati ogni giorno; (4) il flag `contamina_evidenza` con canale operatore immediato; (5) barre a 5 minuti + le quattro marche temporali della notizia, che sbloccano quasi tutto il resto.

Se vuoi, ne scrivo una spec ordinata sotto `docs/superpowers/specs/` — separando esplicitamente ciò che è strumentazione (nessuna deroga) da ciò che tocca il comportamento (deroga necessaria), così è pronta da valutare contro la carta.
