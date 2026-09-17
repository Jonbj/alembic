# S4 source recovery follow-up — 2026-09-07

## Esito

Questa verifica aggiorna il censimento del 2026-09-01 per `ACA005`, `ACA009`,
`MET003`, `MET006` e `NEW001`, senza modificare i manifest e senza avviare il
cluster. Sono state trovate copie istituzionali scaricabili della **Version of
Record** per `ACA009`, `MET003` e `MET006`. Per `ACA005` è disponibile una
bozza pre-pubblicazione della stessa linea di lavoro; per `NEW001` non è emersa
una copia full-text del documento esatto, ma è disponibile un working paper
primario con copertura concettuale parziale.

Le associazioni alle ipotesi sono inferite confrontando i contenuti delle fonti
con il registry [H01–H22](HYPOTHESES.md), perché il
[manifest congelato](SOURCE_MANIFEST.tsv) non dichiara una mappa fonte→ipotesi.
Una fonte non equivalente deve ricevere un ID distinto: non va usata come
sostituzione silenziosa del documento congelato.

## Riepilogo operativo

| ID | Candidato raccomandato | Equivalenza | Accesso verificato il 2026-09-07 | Raccomandazione |
|---|---|---|---|---|
| `ACA005` | [Duke, *News Momentum*, draft 2019](https://ipl.econ.duke.edu/seminars/system/files/seminars/2516.pdf) | Stessa linea di ricerca e stessi autori, ma titolo/versione precedenti alla pubblicazione | HTTP 200, PDF 47 pp., 3,187,729 byte | Ingerire solo come fonte nuova versionata; lasciare `ACA005` indisponibile |
| `ACA009` | [LSE Research Online, Published Version](https://researchonline.lse.ac.uk/id/eprint/122592/1/1_s2.0_S1544612324002575_main.pdf) | Version of Record esatta | HTTP 200, PDF 10 pp., 1,087,537 byte, CC BY 4.0 | Ammissibile sotto `ACA009`, dopo correzione controllata del manifest |
| `MET003` | [University of Zurich, articolo Econometrica](https://www.econ.uzh.ch/dam/jcr%3Affffffff-935a-b0d6-ffff-ffffa286d4d1/etca.pdf) | Version of Record esatta | HTTP 200, PDF 46 pp., 315,991 byte | Ammissibile sotto `MET003` |
| `MET006` | [sito dell'autore Brad Barber, articolo JF](https://www.bradmbarber.com/s/JF_Improved.pdf) | Version of Record esatta | HTTP 200, PDF 37 pp., 217,352 byte | Ammissibile sotto `MET006` |
| `NEW001` | [AEA, Wang–Zhang–Zhu, *The Momentum of News*](https://www.aeaweb.org/conference/2017/preliminary/paper/G46EGhsb) | Studio diverso con sovrapposizione tematica | HTTP 200, PDF 44 pp., 683,278 byte | Ingerire solo con ID nuovo; lasciare `NEW001` indisponibile |

## Verifica per fonte

### `ACA005` — *Pervasive Underreaction: Evidence from High-Frequency Data*

**Identità congelata.** Hao Jiang, Sophia Zhengzi Li e Hao Wang, *Journal of
Financial Economics* 141(2), 573–599 (2021), DOI
[`10.1016/j.jfineco.2021.04.003`](https://doi.org/10.1016/j.jfineco.2021.04.003),
PII `S0304405X21001306`. Il record
[ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0304405X21001306)
e il [record Rutgers](https://www.researchwithrutgers.org/en/publications/pervasive-underreaction-evidence-from-high-frequency-data/)
confermano identità e pubblicazione. La versione SSRN 2679614 risulta revisionata
il 22 marzo 2021 e indicata come JFE forthcoming, ma il PDF continua a restituire
HTTP 403 nelle richieste dirette.

**Candidato.** Il repository seminariale della Duke University ospita
[*News Momentum*, draft 6 agosto 2019](https://ipl.econ.duke.edu/seminars/system/files/seminars/2516.pdf),
di Jiang, Li e Wang. È una versione precedente della stessa linea di lavoro:
usa news firm-level ad alta frequenza, scompone i return in news/non-news,
misura continuation nella settimana successiva e studia distrazione degli
investitori e lentezza degli analisti. Il titolo, la data e la versione
precedono però la peer review finale; risultati numerici, specifiche e robustezze
non possono essere assunti identici alla VoR 2021.

**Copertura attesa.** `H02`, `H04` e `H22`; qualifica `H07`. La trasferibilità a
S4 resta limitata perché il segnale è la reazione iniziale di prezzo, non un
sentiment score prodotto da un modello contestuale, e la strategia è long-short.

**Raccomandazione.** Non sostituire `ACA005`. Aggiungere il draft Duke con un ID
nuovo e versione esplicita se serve copertura immediata; mantenere aperta la
ricerca della VoR o dell'SSRN 2021 legalmente scaricabile.

SHA-256 del candidato verificato: `dac68f8c2831278c89c86f2cf2e2d9f618ae734df153418479b12e65475d59aa`.

### `ACA009` — *Sentiment Trading with Large Language Models*

**Identità congelata.** Kemal Kirtac e Guido Germano, *Finance Research
Letters* 62, 105227 (2024), DOI
[`10.1016/j.frl.2024.105227`](https://doi.org/10.1016/j.frl.2024.105227).
Il precedente URL del manifest usa per errore SSRN `4766886`; il record corretto
è [SSRN 4706629](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4706629).

**Candidato esatto.** [LSE Research Online](https://researchonline.lse.ac.uk/id/eprint/122592/)
fornisce il PDF dell'articolo pubblicato. La copertina del repository dichiara
`Version: Published Version` e licenza `Creative Commons: Attribution 4.0`; il
PDF contiene volume, article number e DOI esatti. È quindi superiore
all'accepted manuscript UCL individuato nella verifica precedente.

**Copertura attesa.** Principalmente `H19`, secondariamente `H02`; qualifica
`H12`–`H14` perché i risultati derivano da backtest, confronto di modelli e
assunzioni su costi e costruzione del portafoglio.

**Raccomandazione.** Usare la copia LSE come rappresentazione esatta di
`ACA009`, registrando provenienza, hash e correzione dell'identificativo SSRN.

SHA-256 verificato: `750aaa3ba6800e81515a1f4bfc9ec49379decb70cf3358fb045baf3b9bff09cc`.

### `MET003` — *Stepwise Multiple Testing as Formalized Data Snooping*

**Identità congelata.** Joseph P. Romano e Michael Wolf, *Econometrica* 73(4),
1237–1282 (2005), DOI
[`10.1111/j.1468-0262.2005.00615.x`](https://doi.org/10.1111/j.1468-0262.2005.00615.x).

**Candidato esatto.** La [University of Zurich](https://www.econ.uzh.ch/dam/jcr%3Affffffff-935a-b0d6-ffff-ffffa286d4d1/etca.pdf)
ospita il PDF completo con frontespizio *Econometrica*, volume 73, numero 4,
luglio 2005 e pagine 1237–1282. Una seconda copia istituzionale identica per
identità è disponibile presso la
[University of Wisconsin](https://users.ssc.wisc.edu/~behansen/718/RomanoWolf2005.pdf).
La VoR elimina il rischio di versione associato al working paper UPF 712 del
2003 già censito.

**Copertura attesa.** `H13`: familywise error rate, confronto simultaneo di più
strategie e bootstrap che conserva la dipendenza fra statistiche.

**Raccomandazione.** Usare la copia University of Zurich sotto `MET003` e
conservare Wisconsin come URL di riserva.

SHA-256 verificato: `70954e9cf3567018ab47e6f0d02c114e99f7e18a721569e331f97d9792651743`.

### `MET006` — *Improved Methods for Tests of Long-Run Abnormal Stock Returns*

**Identità congelata.** John D. Lyon, Brad M. Barber e Chih-Ling Tsai, *The
Journal of Finance* 54(1), 165–201 (1999), DOI
[`10.1111/0022-1082.00101`](https://doi.org/10.1111/0022-1082.00101).

**Candidato esatto.** La pagina first-party
[Published Papers di Brad Barber](https://www.bradmbarber.com/published-papers)
collega una copia completa dell'articolo
([PDF](https://www.bradmbarber.com/s/JF_Improved.pdf)). Il frontespizio riporta
*The Journal of Finance*, vol. LIV, n. 1, febbraio 1999, titolo, tre autori e
pagina iniziale 165. La copia è la VoR ed è distinta dal vecchio mirror NYU ora
in 404 e dalla bozza SSRN 11198 incompleta.

**Copertura attesa.** `H07` e `H04`; qualifica `H18`. Il documento mostra i
rischi di misspecificazione dei long-run abnormal-return test dovuti a new
listing/survivorship, rebalancing, skewness, dipendenza cross-sectional e modello
di asset pricing.

**Raccomandazione.** Usare la copia collegata dall'autore sotto `MET006`. Non è
esposta una licenza open; usarla per lettura/estrazione non implica permesso di
redistribuzione.

SHA-256 verificato: `d99ddb2739f9561d048fdd7ba8637189b7e6ab1f62140c395d7277b3836bdd6d`.

### `NEW001` — *The Persistence of News Sentiment: Implications for Return Predictability*

**Identità congelata.** Dilan Aksoy-Yurdagul, Axel Buchner e Abalfazl Zareei,
*Economics Letters* 260, 112803 (2026), DOI
[`10.1016/j.econlet.2025.112803`](https://doi.org/10.1016/j.econlet.2025.112803),
PII `S0165176525006408`. Il
[record publisher](https://www.sciencedirect.com/science/article/abs/pii/S0165176525006408)
descrive RavenPack US 2000–2023, continuation di breve e reversal dopo
persistenza lunga. [IDEAS/RePEc](https://ideas.repec.org/a/eee/ecolet/v260y2026ics0165176525006408.html)
conferma che il full text resta riservato agli abbonati; non è stato trovato un
author manuscript immediatamente scaricabile.

**Candidato parziale.** Il working paper primario di Ying Wang, Bohui Zhang e
Xiaoneng Zhu,
[*The Momentum of News*](https://www.aeaweb.org/conference/2017/preliminary/paper/G46EGhsb),
è ospitato dall'American Economic Association. Usa RavenPack firm-level USA,
misura persistenza del sentiment, separa hard/soft news, testa size, analyst
coverage e institutional ownership e collega news momentum a return
predictability. Non è però lo stesso studio: autori e campione sono diversi,
l'aggregazione principale è mensile, il periodo è 2000–2014 e non replica la
distinzione aggiornata tra momentum breve e reversal da persistenza lunga.

**Copertura attesa.** Parziale per `H02`, `H06`, `H20` e `H22`; non sostituisce
l'evidenza specifica di `NEW001` per `H03`–`H04`.

**Raccomandazione.** Conservare `NEW001` come non disponibile e ingerire il
working paper AEA solo con un nuovo ID. La conclusione specifica di `NEW001`
deve restare non verificata finché non è disponibile il testo esatto o un
manoscritto d'autore autorizzato.

SHA-256 del candidato parziale verificato: `6e6942f02e598565c10e59cacf56b1310f44ba06f6da6e24d0acc08acef85b28`.

## Decisione proposta

Il prossimo lotto può includere immediatamente le copie esatte di `ACA009`,
`MET003` e `MET006`. `ACA005` e `NEW001` richiedono invece nuovi ID versionati
per i candidati parziali; i due ID originali devono rimanere indisponibili. In
questo modo il cluster può colmare parte della copertura senza confondere
equivalenza bibliografica e somiglianza tematica.
