# S4 orizzonte economico — risposta di glm52

**Modello:** glm52 (Ollama Cloud) · **Data:** 2026-08-13 · **Riferimento:** issue #242, prompt
`docs/S4_DECISIONE_ORIZZONTE_PROMPT_ESTERNO_2026-08-13.md`

## Ragionamento (sintesi prima del blocco strutturato)

La decisione non è «quale orizzonte ha S4», ma «su quali证据 possiamo scegliere un orizzonte
adesso». Tre fatti del documento, tutti in §3.2/§3.5/§3.6/§6, restringono il campo:

1. **L'IC si misura senza tradere.** È una correlazione Spearman cross-sectional fra segnale e
   forward return. Non serve capitale a rischio per stabilire se c'è alpha. Dunque non c'è
   ragione di tenere S4 in esecuzione mentre la misura è incoerente.
2. **Le uscite attuali sono rotte (QS-07/FIX-D, §2).** Il P&L realizzato di S4 in esecuzione
   misura una strategia con uscite difettose, non la strategia che qualunque opzione
   proporrebbe. In particolare il P&L *live* non è informativo per l'opzione B, che richiede una
   regola d'uscita esplicita nuova. Misurare B in esecuzione richiede di deployare B — un
   cambio di comportamento — su dati sporchi e sotto potenza.
3. **IC su dati sporchi, n=38, orizzonte 1/3/5g su una sleeve che dura 4h15.** Il criterio di
   kill #179 misura un orizzonte che la strategia non ha mai avuto, su dati non ancora corretti.
   Sopravvivere a un test incoerente (media IC +0,0078) non è evidenza di vita: è rumore che
   passa una soglia mal posta.

L'opzione A è strutturalmente debole: §3.4 mostra che al primo segnale il 70–84% del movimento
intraday è già avvenuto. Comprare su news editoriale a orizzonte 1–4h significa comprare dopo il
movimento, con un rapporto costi/alpha già al 32% (§4A) che peggiora accorciando l'orizzonte, e
richiede infrastruttura event-driven che non esiste (§5.3) e non si deploya come singolo cambio
datato. A non è un'opzione deployabile oggi; è un programma di ricerca.

L'opzione B è la più onesta strutturalmente — è l'unica che *ripara* il difetto (uscita esplicita
al posto delle quattro uscite implicite) e allinea orizzonte della strategia e orizzonte della
misura. Ma committe capitale per 1–3 giorni su una sleeve il cui IC a 3g è +0,013
(indistinguibile da zero), con sovrapposizione S1 non smentita (n=30, §5.6), prima che i dati
siano puliti e prima che n basti a distinguere 0,05 da 0. B è la scelta giusta *dopo* aver
misurato, non *per* misurare.

L'opzione C (shadow) è l'unica delle tre che rispetta la struttura a due stadi
(misura-su-pulito → scegli orizzonte): conserva la serie, azzera costi/interferenza, libera il
10%, e — punto chiave — **permette di misurare IC e P&L simulato su dati puliti all'orizzonte di
B senza rischiare capitale e senza deployare uscite nuove su una strategia non validata**. Il
downside che il documento attribuisce a C («rinuncia all'unica sleeve con P&L realizzato
positivo») è caricato: +209 $ su n=81, dati sporchi, uscite rotte, IC sotto potenza non sono
evidenza di alpha; e shadow *continua a misurare*, non «chiude la questione».

Atterra quindi su C, non come verità finale ma come unico passo onesto prima di avere la misura
coerente. La scelta orizzonte (A/B/kill) si prende dopo, su dati puliti, con un criterio
pre-registrato coerente. Sotto, il blocco strutturato.

---

```
SCELTA:            C — non perché S4 abbia fallito (il criterio #179 è incoerente: orizzonte
                   sbagliato + dati sporchi, quindi il suo verdetto «sopravvive» è privo di valore),
                   ma perché l'alpha non è misurabile oggi e l'IC è misurabile senza tradere:
                   tenere capitale a rischio su una sleeve non validata, con uscite rotte e dati
                   sporchi, non aggiunge informazione che shadow già non fornisca. C è lo stage-1
                   di una decisione a due stadi, non il verdetto finale.

CONFIDENZA:        media — il ragionamento (IC misurabile offline; uscite live rotte → P&L live
                   non informativo per B; dati sporchi; n=38 sotto potenza) è robusto e tutto
                   interno al documento. Non alta perché due contro-segnali reali esistono: il
                   P&L realizzato positivo di S4 sulla vita intera (+209 $, 53% win) e l'IC del
                   sottoinsieme ad alta convinzione (≥0,30: +0,0465 a 3g, l'unico valore coerente
                   positivamente non-significativo). Entrambi potrebbero indicare un segnale
                   debole ma reale all'orizzonte di B, che C posticipa invece di testare in
                   esecuzione. La posta in gioco (10% del NAV per ~6 settimane di optionality
                   perso) è modesta, ma non nulla.

CRITERIO DI FALSIFICAZIONE:  La scelta C è falsificata (ero troppo conservativo → avrei dovuto
                   tenere S4 in esecuzione come B) se, su dati PULITI post-deploy #236/#242, in
                   shadow, simulando le would-be trade di B (regola d'uscita esplicita, orizzonte
                   1–3g, same sizing 2%/slot), si osserva SU ≥40 sedute pulite: (a) P&L simulato
                   netto post-costi > 0 con lower bound del CI bootstrap al 95% > 0, E (b) IC
                   solo-ensemble a 3g ≥ 0,05 con t ≥ 2 (o CI bootstrap per giorno esclude 0).
                   Entrambe → invertire C e riabilitare come B. Nessuna delle due entro n=73
                   sedute pulite → kill definitivo (non più shadow). Misurabile su dati che
                   avremo, non su dati che già abbiamo: manca il deploy pulito e ~40 sedute
                   aggiuntive (raggiungibili entro/passata la fine del freeze 28/09).

RIMISURA DELL'IC:  Orizzonte: 1, 3, 5 giorni trading (orizzonte candidato di B) — NON 1h/4h/close,
                   perché A è escluso e misurare l'orizzonte intraday di una sleeve che non
                   intendiamo tenere spreca potenza. Metodo: (1) primario = Spearman cross-section
                   POOL su tutti i symbol-day puliti, n = simboli(96)×giorni, con cluster
                   bootstrap per giorno (corregge l'autocorrelazione del panello) — rileva IC
                   ~0,02–0,03, un ordine di grandezza sotto il minimo rilevabile della serie
                   giornaliera attuale; (2) confirmatory = serie di IC giornalieri con t-test,
                   come oggi, come guardrail indipendente. Separa sempre solo-ensemble vs
                   solo-FinBERT (FinBERT è la sorgente di rumore: −0,03/−0,08) e stratifica per
                   alta convinzione (≥0,30). Solo su dati post-#236/#242. n minimo: 60 sedute
                   pulite per il pooled (≈5.760 oss, sufficienti al bootstrap); 90 sedute pulite
                   per il t-series confirmatory (≈38 × (0,12/0,05)² × (2/3)² ≈ 96, arrotondato a
                   90). n=38 attuale è sotto entrambi.

L'EVIDENZA BASTA?  No. Mancano: (1) dati puliti — #236/#242 non deployati, e una parte non
                   quantificata dell'IC≈0 è attribuibile a rumore a monte (§3.6: 51/96 simboli
                   senza news, 49,6% righe da articoli multi-ticker, MS 97% falsi positivi);
                   (2) IC coerente con orizzonte e con potenza adeguata — n=38 non distingue
                   0,05 da 0; (3) una regola d'uscita onesta, perché il P&L live attuale riflette
                   uscite rotte, non una strategia reale; (4) un controfattuale di entry non
                   leaking — il delta «all'apertura» +196,68 $ usa informazione futura (§6.4).
                   Tempo: il deploy pulito è «in corso»; restano ~40 sedute di freeze →
                   raggiungo n≈60–70 pulite entro/passando il 28/09, sufficienti al pooled ma non
                   al t-series. Basta per PRE-REGISTRARE il criterio e iniziare la misura; NON
                   basta per DECIDERE entro il 28/09. La decisione slitta oltre la fine del
                   freeze — il che va dichiarato come implicazione di governance, non taciuto.

SEQUENZA DI DEPLOY:  Un singolo batch datato, ora, che raggruppa: (a) deploy correzioni #236/#242
                   (input pulito), (b) flip S4 → shadow, (c) pre-registrazione del criterio
                   coerente (pooled IC + P&L simulato B, soglie e n sopra). Motivo: ogni deploy
                   separato è una discontinuità (§5.5); raggruppare = una sola discontinuità,
                   poi un segmento pulito lungo e confrontabile in shadow. Pre-batch = S4 live
                   su dati sporchi (serie storica di riferimento, così com'è); post-batch = S4
                   shadow su dati puliti (serie di misura). Poi: sola osservazione fino a
                   criterio valutato. Infine, secondo batch datato solo se il criterio si
                   innesca (riabilita come B: uscita esplicita + orizzonte 1–3g) o, terzo
                   esito, kill. Nessuno spread su più giorni; ogni cambio è un unicum datato.

COSA HO IGNORATO:  - I 9 trade della finestra (−89,12 $) e i cluster 1h45/4h15: non usati per
                   decidere — §3.2 li dichiara la settimana peggiore su cinque, n=9 non
                   rappresentativo. Usati solo come conferma che il difetto meccanico è reale.
                   - Entry percentile (64,3°) e delta «compra all'apertura» +196,68 $: ignorati,
                   §6.4 — usa informazione futura, non realizzabile, è decomposizione non
                   proposta.
                   - t = −4,96 alle 14 UTC: ignorato, §6.7 — test invalido (coorte legacy + un
                   solo giorno).
                   - Confronto P&L realizzato S4 vs S1 (+209 vs −769): NON usato come evidenza
                   che S4 sia migliore, §6.6 — S1 avversamente selezionato. Usato solo al
                   negativo: il +209 $ non è ragione sufficiente per continuare a tradere.
                   - Frazione di movimento intraday già avvenuta (82%): USATA, ma per escludere
                   A (news arriva a movimento fatto → intraday debole), non per sceglierla.
                   - Breakdown P&L per settimana: usato solo per confermare che n=9 è la
                   settimana peggiore (non per estrarre un trend).

DISSENSO:          - La descrizione del downside di C («rinuncia all'unica sleeve con P&L
                   realizzato positivo») è caricata e confonde shadow con kill: +209 $ su n=81
                   con dati sporchi, uscite rotte e IC sotto potenza non sono evidenza di alpha;
                   e shadow continua a misurare, non «chiude la questione senza misurare su
                   dati puliti». Il documento applica a C la critica che varrebbe per un kill.
                   - Il criterio #179 è presentato come un test che S4 «sopravviverebbe» per
                   rumore. Dissento più radicalmente: un criterio misurato sull'orizzonte
                   sbagliato e su dati sporchi è void a prescindere dal segno. Sopravvivere a
                   un test incoerente non è segnale di vita; il fatto che la media venga +0,0078
                   non va letto come «S4 passa per un pelo» ma come «il test non sta misurando
                   ciò che dovrebbe». Il documento lo ammette a metà («rumore puro») ma ne
                   conserva la cornice di verdetto.
                   - Il documento tratteggia lo spazio di scelta come tre opzioni e chiede una
                   «quarta» solo se nessuna va. La decisione reale è a due stadi (misura-su-
                   pulito → scegli orizzonte); forzare la scelta di orizzonte ORA, prima di
                   dati puliti e n adeguato, è prematura per A e B alike. C è l'unica delle tre
                   che rispetta la struttura a due stadi — ed è per questo che ci attero, non
                   perché C sia «la risposta». È un'osservazione di metodo, non un'opzione
                   extra.
                   - §3.4 (82% di movimento già fatto) è usato univocamente come «la news è in
                   ritardo». È anche compatibile con news coincidente e prezzo che REAGISCE, e
                   i casi >100% (ORCL 110,8%, NOK 121,1%) suggeriscono revert dopo il segnale —
                   che taglia in entrambi i versi e, letto come reversione, favorirebbe B
                   (1–3g). Il documento sottappesaa questa lettura alternativa. Non cambio la
                   scelta (dati sporchi + sotto potenza prevalgono), ma l'uso di questo numero
                   è unilaterale.
```