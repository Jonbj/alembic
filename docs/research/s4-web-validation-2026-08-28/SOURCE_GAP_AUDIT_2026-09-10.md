# S4 source-gap audit — 2026-09-10

## Esito

La ricerca, limitata a publisher, autori, repository universitari e sedi
accademiche first-party, **non ha prodotto una copia full-text esatta che il
coordinatore possa congelare e ingerire automaticamente** per `ACA005` o
`NEW001`.

- Per `ACA005` esiste un manoscritto con titolo e autori esatti su SSRN, ma il
  PDF restituisce HTTP 403/Cloudflare al verificatore. La Version of Record
  Elsevier resta ad accesso riservato.
- Per `NEW001` il publisher e le pagine istituzionali degli autori confermano
  l'identità bibliografica, ma non espongono un manoscritto o PDF pubblico.

Sono invece verificati tre documenti accademici primari, pubblicamente
scaricabili e distinti. Possono entrare in un lotto successivo solo con **nuovi
ID e versione dichiarata**. Nessuno dei tre deve sostituire silenziosamente
`ACA005` o `NEW001`.

## Criterio di priorità sulle lacune H01–H22

Come indicatore preliminare, non come verdetto finale, le card locali v4
contengono zero claim grezzi per `H09`, `H12`, `H16` e `H17`, e un solo claim
per `H01`, `H03`, `H10`, `H11` e `H15`. I tre candidati sotto sono prioritari
perché recuperano parte dell'evidenza persa con `ACA005`/`NEW001` e rafforzano
in particolare `H01`, `H02`, `H04`, `H09`, `H15`, `H19`, `H20` e `H22`.
Le associazioni fonte→ipotesi sono inferenze da verificare nel protocollo
evidence-bound, non conclusioni già convalidate.

## Verifica delle due identità congelate

### `ACA005` — *Pervasive Underreaction: Evidence from High-Frequency Data*

Il [record del publisher](https://www.sciencedirect.com/science/article/pii/S0304405X21001306)
identifica Hao Jiang, Sophia Zhengzi Li e Hao Wang, *Journal of Financial
Economics* 141(2), 573–599 (2021), DOI
[`10.1016/j.jfineco.2021.04.003`](https://doi.org/10.1016/j.jfineco.2021.04.003).
Il [record istituzionale Rutgers](https://www.researchwithrutgers.org/en/publications/pervasive-underreaction-evidence-from-high-frequency-data/)
conferma titolo, autori, rivista, volume, fascicolo e pagine, ma non offre un
allegato full-text.

La [pagina SSRN 2679614](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2679614)
registra un manoscritto di 62 pagine, stesso titolo e stessi autori, revisionato
il 22 marzo 2021 e indicato come JFE forthcoming. È dunque una versione
pre-pubblicazione identificabile della stessa opera, non la Version of Record.
SSRN dichiara «all rights reserved» e presenta un link di download, ma sia la
pagina sia l'endpoint PDF hanno restituito HTTP 403 con challenge Cloudflare il
2026-09-10. Non è stato quindi possibile acquisire i byte, verificarne l'hash o
congelarne il testo per il cluster.

**Stato:** copia esatta nota, ma non operativamente accessibile; mantenere
`ACA005` indisponibile finché non si ottiene il PDF SSRN in modo autorizzato o
un deposito istituzionale equivalente.

### `NEW001` — *The Persistence of News Sentiment: Implications for Return Predictability*

Il [record del publisher](https://www.sciencedirect.com/science/article/abs/pii/S0165176525006408)
identifica Dilan Aksoy-Yurdagul, Axel Buchner e Abalfazl Zareei, *Economics
Letters* 260, 112803 (2026), DOI
[`10.1016/j.econlet.2025.112803`](https://doi.org/10.1016/j.econlet.2025.112803).
Le pagine first-party di [Dilan Aksoy-Yurdagul](https://escp.eu/it/node/81765)
e [Axel Buchner](https://escp.eu/faculty-research/faculty-members/buchner-axel)
elencano la stessa pubblicazione, ma non collegano un file full-text. Il
publisher offre abstract e metadati, non un PDF pubblico; l'endpoint PDF ha
restituito HTTP 403 il 2026-09-10. Non è emerso un deposito SSRN, arXiv,
istituzionale o personale con titolo/autori/DOI corrispondenti.

**Stato:** nessuna copia full-text esatta verificata; mantenere `NEW001`
indisponibile. La conclusione specifica su momentum breve e reversal dopo
persistenza lunga resta non verificabile dal solo abstract.

## Tre fonti distinte candidate

### 1. Jiang, Li e Wang — *News Momentum*, draft 6 agosto 2019

- **URL first-party:** [Duke University PDF](https://ipl.econ.duke.edu/seminars/system/files/seminars/2516.pdf)
- **Accesso verificato:** HTTP 200, `application/pdf`, 47 pagine, 3.187.729
  byte.
- **SHA-256:** `dac68f8c2831278c89c86f2cf2e2d9f618ae734df153418479b12e65475d59aa`
- **Identità/versione:** il frontespizio riporta *News Momentum*, Hao Jiang,
  Sophia Zhengzi Li e Hao Wang, «This Draft: August 6, 2019». È un antecedente
  della stessa linea di lavoro di `ACA005`, ma titolo, data, specifiche e
  risultati precedono il manoscritto SSRN 2021 e la VoR JFE.
- **Copertura attesa:** `H02`, `H05`, `H07` e `H22`; qualifica `H04`. Usa news
  firm-level timestamped e return a intervalli di 15 minuti, trova drift nei
  giorni successivi, stima alpha factor-adjusted e studia distrazione e lentezza
  degli analisti. Non convalida l'orizzonte esatto T+63 di S4.
- **Vincolo:** nuovo ID obbligatorio; il server Duke non espone una licenza open
  esplicita, quindi accesso per analisi non implica diritto di redistribuzione.

### 2. Wang, Zhang e Zhu — *The Momentum of News*, draft dicembre 2016

- **URL first-party:** [American Economic Association PDF](https://www.aeaweb.org/conference/2017/preliminary/paper/G46EGhsb)
- **Accesso verificato:** HTTP 200, `application/pdf`, 44 pagine, 683.278 byte.
- **SHA-256:** `6e6942f02e598565c10e59cacf56b1310f44ba06f6da6e24d0acc08acef85b28`
- **Identità/versione:** il frontespizio riporta *The Momentum of News*, Ying
  Wang, Bohui Zhang e Xiaoneng Zhu, «This Draft: December 2016». È un
  conference/working paper distinto da `NEW001`: cambiano autori, campione,
  frequenza e disegno.
- **Copertura attesa:** `H02`, `H06`, `H20`, `H21` e `H22`; qualifica `H09`.
  Studia persistenza del sentiment RavenPack, hard versus soft news, size,
  analyst coverage e institutional ownership; riferisce robustezza
  all'inclusione delle news neutrali e rendimenti su news e non-news days. Non
  costruisce però il controllo matched no-news richiesto da `H09` e non replica
  la non-linearità breve/lunga di `NEW001`.
- **Vincolo:** nuovo ID obbligatorio; la sede AEA rende il PDF pubblico ma non
  espone nel documento una licenza di redistribuzione.

### 3. Malo et al. — *Good Debt or Bad Debt*, arXiv v2 del 23 luglio 2013

- **URL first-party:** [arXiv record e PDF](https://arxiv.org/abs/1307.5336)
- **Accesso verificato:** HTTP 200, `application/pdf`, 15 pagine, 2.844.686
  byte.
- **SHA-256:** `b8de2b31a9b13faf15bd27ee26d92ec60b9e62eb641f674ca11ab0b9a0ef886c`
- **Identità/versione:** arXiv `1307.5336v2`, Pekka Malo, Ankur Sinha, Pyry
  Takala, Pekka Korhonen e Jyrki Wallenius. Il
  [record istituzionale Aalto](https://research.aalto.fi/fi/publications/good-debt-or-bad-debt-detecting-semantic-orientations-in-economic/)
  collega la linea di lavoro all'articolo peer-reviewed 2014, DOI
  [`10.1002/asi.23062`](https://doi.org/10.1002/asi.23062); il candidato è la
  versione arXiv dichiarata, non la VoR Wiley.
- **Copertura attesa:** `H01`, `H15`, `H19` e `H21`. Costruisce un benchmark di
  circa 5.000 frasi finanziarie con 5–8 giudizi per frase da 16 annotatori,
  misura l'accordo, forma gold standard a più soglie e confronta un modello
  contestuale con baseline word-count. Qualifica `H15`: campionamento e
  overlapping annotation sono utili, ma la coorte è OMX Helsinki e il paper non
  documenta cecità rispetto agli output S4 né rappresentatività del suo universo
  live.
- **Vincolo:** nuovo ID obbligatorio e versione `arXiv v2` esplicita.

## Decisione operativa proposta

Congelare, se autorizzato, i tre PDF con nuovi ID e sottoporli al normale
passaggio node1→node2. Lasciare invariati `ACA005` e `NEW001`. Dopo il
consolidamento, le aree ancora probabilmente scoperte sono `H10` (available-at),
`H11` (score versioning), `H12` (forward untouched), `H16` (first loss cause) e
`H17` (ruolo della gamba negativa). In particolare `H11`, `H16` e `H17` hanno
una forte componente di contratto interno S4: la letteratura può qualificare la
scelta, ma non sostituisce evidenza di pipeline e una decisione di policy.

Questa verifica non ha modificato manifest, ledger, output del cluster o codice,
e non ha usato Llama/Ollama locale né avviato servizi.
