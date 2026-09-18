# Pre-registrazione — backtest news 2024-2025 (issue #610)

Scritta il **2026-09-17**, **prima del primo download**. Da qui non si modifica: un'ipotesi
aggiunta dopo aver visto i dati non è un'ipotesi, e una classe aggiunta alla tassonomia di
H-B dopo i risultati invalida H-B.

Issue: [#610](https://github.com/Jonbj/alembic/issues/610) · Parte di #21 ·
Evidenza di partenza: `docs/research/2026-09-16-s4-event-study-latenza.md`
Test live gemello, **non** sostituito da questo lavoro: #606

## 0. Cosa misura questo lavoro, e cosa no

Misura se **esiste segnale nelle news Benzinga su questo universo**. Non misura se il
nostro prompt DK-CoT lo cattura: lo scoring qui è FinBERT locale, non l'ensemble di
produzione (§5). Chi legge un esito di questo artefatto e conclude qualcosa sulla qualità
dei nostri prompt sta leggendo il numero sbagliato.

La Fase 1 risponde a *«esiste un'associazione?»*. La Fase 2 — che **non parte** se la Fase
1 non lascia una popolazione che valga la pena simulare — risponde a *«avremmo
guadagnato?»*. Il cancello fra le due è parte del disegno: se non resta niente da
simulare, **quella è la risposta**, non un fallimento.

## 1. Dati

- **News:** endpoint storico Alpaca (Benzinga), `include_content=true`, paginato con
  `next_page_token`. Si riusa la paginazione di `src/connectors/alpaca_news.py`
  (regola #169/#467: si importa, non si ricopia).
- **Finestra della popolazione:** articoli **creati** (`created_at`) fra `2024-01-01` e
  `2025-12-31`. **Il 2026 resta fuori**: è la finestra live su cui abbiamo già formato
  un'opinione, e rientrare dentro significherebbe misurare due volte lo stesso campione.
- **Finestra della paginazione:** `2024-01-01` → **data di scaricamento**, perché
  l'API filtra su `updated_at` (§1.2). È un sovrainsieme, dato che
  `updated_at >= created_at` sempre. Il manifest registra entrambe.
- **Universo:** i 96 simboli di `config/trading.yaml` → `symbols.watchlist`.
- **Prezzi:** Alpaca, `feed=SIP`, `adjustment=ALL`. Una sola fonte (§7).
- **Persistenza:** tabelle o file **propri**. Zero scritture su `news_log`,
  `sentiment_signals`, `news_resolved_entities`, Redis.

### 1.1 Fail-closed sul fetch — non è teorico

Alpaca rifiuta l'**intera** richiesta con `subscription does not permit querying recent
SIP data` se la finestra tocca l'embargo sul dato recente. Nel pilota del 2026-09-16 ha
eliminato **proprio i simboli più liquidi** (AAPL, MSFT, GOOGL, META, NVDA…), portando n
da 330 a 68 e **gonfiando l'effetto da +0,678% a +0,936%**: una finestra troncata non
degrada il risultato, lo *migliora*, ed è per questo che deve abortire invece di
proseguire.

**Regola: fetch fallito ⇒ abort.** Nessun risultato parziale, nessun simbolo saltato in
silenzio. Un test asserisce che una pagina fallita interrompe la raccolta e non produce
artefatto.

### 1.2 La finestra dell'API non è la finestra della popolazione

Misurato il **2026-09-17** contro l'API vera, prima di qualunque misura:
**`start`/`end` filtrano su `updated_at`, non su `created_at`.**

Su una sola settimana (2024-03-01→08), **14 articoli su 880** erano stati *creati* anni
prima e solo ritoccati dentro la finestra. E non a caso: «3 Outdoor Stocks To Watch For
Summer 2020», «NFT Craze A Reminder Of Tulip Mania?», «Did Billionaire Elon Musk Sell All
His Mansions». Sono evergreen e listicle, cioè **esattamente la classe che H-A e H-B
devono misurare**: la contaminazione carica un gruppo solo, non tutti, e avrebbe reso
H-A più facile da far passare.

Difetto speculare, misurato: un articolo creato a fine 2025 ma aggiornato nel 2026 non
comparirebbe mai in una finestra ferma al 2025-12-31 (5 articoli nel solo 2026-01).

Perciò: si pagina su `updated_at` fino alla data di scaricamento, e la popolazione si
ritaglia su `created_at`. L'archivio su disco resta grezzo; il ritaglio è a valle,
importabile e testato (`dentro_popolazione`).

### 1.3 Lo scaricatore

Idempotente e ripartibile: rieseguirlo non duplica righe e riprendere dopo
un'interruzione non richiede di riscaricare ciò che è già a terra. L'identità
dell'articolo è l'`id` Alpaca.

## 2. Le due popolazioni, dichiarate prima

**L'archivio non è quello che abbiamo ingerito.** La pipeline live applica risoluzione
ticker, deduplica e filtro di staleness che uno scarico grezzo non riproduce.

Ogni esito si pubblica **sempre in coppia**:

- **archivio** — tutti gli articoli come li serve Alpaca;
- **ricostruita** — i filtri deterministici del live applicati riusando il codice di
  produzione (`src/connectors/deduplicator.py`, `_is_stale_news` di
  `src/workers/sentiment.py`), **importato, non ricopiato**.

Se divergono, **la divergenza è un risultato**, non un fastidio da appianare.

### 2.1 Un terzo filtro, trovato leggendo il codice e dichiarato qui

`AlpacaNewsConnector._parse_article` restituisce `None` quando `summary` e `content` sono
entrambi vuoti: **la pipeline live scarta del tutto quegli articoli**. È una cosa diversa
dal detector `CONTENT_EMPTY`, che riconosce template *con* testo. La popolazione
ricostruita applica anche questo scarto, e il conteggio dei due gruppi va pubblicato
separatamente nell'artefatto di copertura — altrimenti H-A misurerebbe un gruppo che il
live non vede nemmeno.

## 3. L'artefatto di copertura viene prima degli esiti

Si pubblica **prima** di qualunque misura: articoli per mese, simboli coperti, quota a
contenuto vuoto, quota multi-ticker, quota fuori orario, e i tre conteggi di popolazione
(archivio / senza corpo / ricostruita). Serve a rendere visibile un buco di copertura
*prima* che diventi un effetto.

## 4. Statistica

- **Unità di inferenza = la giornata.** Un `t` per-evento è un difetto, non una variante:
  gli articoli dello stesso giorno sullo stesso nome non sono osservazioni indipendenti.
- **Rendimenti in eccesso** su SPY, o demediati per seduta. Fa parte della definizione
  dell'outcome, non è un aggiustamento successivo. Il precedente che lo impone è del
  2026-09-16: −0,78% di «news inverse» è diventato +0,06% demediando — era beta, non
  segnale.
- Riduzione a `(simbolo, seduta)` con `scelta_produzione()` di
  `scripts/measure_169_dedup_rules.py`, importata.
- **Holdout temporale:** **2024 = esplorazione** (si sceglie la specifica, si fissa la
  direzione attesa; nulla è riportabile). **2025 = conferma**, eseguita **una volta** con
  specifica congelata. **Solo il 2025 è risultato.**
- **Molteplicità:** Holm-Bonferroni sulla famiglia delle **cinque** ipotesi primarie
  (H-A, H-B, H-C, H-E, H-F). La secondaria è fuori famiglia ed etichettata tale.
- **Sovrapposizione:** oltre le 5 sedute i rendimenti si sovrappongono. Newey-West con
  lag pari all'orizzonte ovunque si pubblichi un `t`.
- Ogni artefatto riporta `effetto_rilevabile_a_t3`: **«non rilevabile» non è «assente»**.

## 5. Scoring: FinBERT locale, e solo quello

`src/llm/finbert.py` (`score_articles`), locale int8. **Nessuna chiamata cloud.** Un LLM
che scora un articolo del 2024 su un'azienda di cui conosce l'esito non prevede,
**ricorda**: il look-ahead non sarebbe nei prezzi ma nei pesi del modello, dove nessun
controllo di causalità lo vedrebbe. Per lo stesso motivo il confronto
ensemble-contro-FinBERT resta sul campione live (#609) e questa issue non lo tocca.

## 6. Contaminazione da selezione nell'universo

`config/trading.yaml:114` dice testualmente *«Added 2026-06-30: off-watchlist names with
recurrent strong ensemble signals (14d)»* — **ROKU, RDDT, HOOD, WDC, SPCX sono nella
watchlist perché producevano segnali forti.** Usarli per misurare se le news producono
segnale è circolare.

Ogni esito si pubblica **anche** senza quei 5 simboli. Se i due numeri divergono, la
watchlist guida il risultato e va detto.

## 7. Prerequisito alla Fase 2: una sola fonte prezzi

`src/backtest/forward_returns.py` usa **yfinance**; tutte le misure live usano Alpaca SIP
`adjustment=all`. Due fonti per la stessa grandezza è la divergenza silenziosa che questo
repo si è già preso più volte. **Va unificata su Alpaca prima che la Fase 2 produca un
solo numero**, e la migrazione va dichiarata come discontinuità.

---

# FASE 1 — le cinque ipotesi, lista chiusa

## H-A · Il detector CONTENT_EMPTY / RETROSPECTIVE separa davvero?

La più urgente: il **28/09** si decide la Leva A di #607 — filtrare quegli articoli — e
oggi quella decisione poggia su **zero** evidenza che il detector classifichi bene.

- **Strumento:** `content_empty_title_reason()` e `classify_timing()` di
  `src/analysis/dossier/article_coverage.py`, deterministici, **importati**.
- **Outcome:** rapporto fra volatilità al minuto nei 5 minuti dopo `created_at` e
  volatilità di fondo (T−30 → T−6), per gruppo.
- **Atteso:** non-CONTENT_EMPTY **> 1**; CONTENT_EMPTY indistinguibile da 1.
- **Esito nullo che conta:** se **nessuno** dei due gruppi mostra un picco, il detector non
  separa niente e la Leva A va riscritta prima di essere decisa.

## H-B · Quali classi di evento muovono il prezzo

Oggi paghiamo inferenza su «Xbox Game Pass March Lineup» come su una trimestrale.

**Tassonomia deterministica dal titolo, scritta qui per intero, prima di vedere i
risultati.** Regole applicate **in quest'ordine**, prima corrispondenza vince; il
confronto è su titolo normalizzato NFKC + casefold.

| # | classe | riconoscimento sul titolo |
|---|---|---|
| 1 | `listicle_recap` | i template `CONTENT_EMPTY` già pre-registrati dalla #508 (`content_empty_title_reason` ≠ None), più: `top \d+ stocks`, `stocks to watch`, `market recap`, `movers`, `what's going on with`, `here's how much` |
| 2 | `earnings` | `\bQ[1-4]\b`, `earnings`, `\bEPS\b`, `quarterly results`, `reports (?:first\|second\|third\|fourth) quarter`, `beats`, `misses`, `revenue` |
| 3 | `guidance` | `guidance`, `outlook`, `forecast`, `\bFY\s?20\d\d\b`, `raises .* view`, `cuts .* view`, `lowers .* view` |
| 4 | `m_and_a` | `acquisition`, `acquires`, `to acquire`, `merger`, `merges`, `takeover`, `to buy`, `stake in`, `divest`, `spin-?off` |
| 5 | `rating_pt` | `upgrade`, `downgrade`, `price target`, `initiates coverage`, `reiterates`, `maintains`, `raises target`, `analyst` |
| 6 | `regulatory_legal` | `\bSEC\b`, `\bFTC\b`, `\bDOJ\b`, `lawsuit`, `sues`, `settlement`, `investigation`, `probe`, `antitrust`, `subpoena`, `recall`, `fine[sd]?\b` |
| 7 | `product_partnership` | `launch`, `unveils`, `introduces`, `partnership`, `partners with`, `collaborat`, `expands` |
| 8 | `other` | tutto il resto |

`listicle_recap` è **prima** di proposito: un articolo intitolato «Here Are The Top 5
Upgrades» è un listicle, non un rating, e metterlo dopo lo farebbe finire in
`rating_pt` gonfiando una classe che ci interessa valutare pulita.

- **Outcome:** rapporto di volatilità come H-A, più il gap in eccesso per classe.
- **Uso:** è la lista di cosa vale la pena scorare — e l'input principale della Fase 2.

## H-C · Il gap fuori orario, fuori campione

- **Popolazione:** `created_at` fuori 09:30–16:00 America/New_York, giorni feriali.
- **Outcome:** `sign(score) × gap_in_eccesso_su_SPY` della prima seduta utile.
- **Riferimento:** il pilota 2026 dà **+0,560%, t 2,35 su 49 giornate** — *candidato, non
  risultato*. Qui si vede se regge su un regime diverso; è il primo test fuori campione
  che quel numero riceve.

## H-E · Le news intraday sono non-eventi

La diagnosi del 2026-09-16 poggia su 742 eventi in 25 sedute; qui ce ne sono ~20.000, e
**deve poter cadere**.

- **Outcome:** curva media allineata al segno fra T−60 e T+60 minuti, più il profilo di
  volatilità al minuto.
- **Atteso (dalla diagnosi in essere):** nessun picco di volatilità a T, intorno a 0,89×
  il fondo. Un picco netto qui **falsifica** la diagnosi corrente, ed è un esito buono
  quanto l'altro.

## H-F · Fan-out: gli articoli multi-ticker portano meno segnale

Risponde a #596 (MU venduta su un titolo che parlava di Western Digital) con una misura
invece che con un aneddoto.

- **Regressore:** `len(symbols)`.
- **Atteso:** effetto per simbolo decrescente in `len(symbols)`.

## Secondaria — fuori dalla famiglia Holm, etichettata tale

**Eterogeneità per titolo.** Il pilota dà dispersione 24,0% contro 18,6% del nulla
(p 0,021) su 26 ticker con n 5-23. Due anni danno l'n per distinguere dispersione da
rumore. **Confondente da testare: il settore** (AMD/AMAT/MU semiconduttori, GS/MS banche),
non il nome — se l'eterogeneità è settoriale, «alcuni ticker reagiscono di più» è una
descrizione sbagliata dello stesso fatto.

---

# FASE 2 — vincoli, dichiarati ora

Non parte finché la Fase 1 non ha prodotto una popolazione da simulare. Quando parte:

1. **Vincolo di capitale.** Il capitale è finito: tenere X significa non comprare Y. Un
   confronto «tenuto X» contro «venduto e cash» prezza un portafoglio a capitale infinito
   e dice quasi sempre che avremmo dovuto tenere. `src/backtest/engine/portfolio.py`
   esiste: va usato, non aggirato.
2. **Costi e slippage dal modello esistente** (`src/backtest/costs/`), mai zero. Un
   segnale da 56 bp non sopravvive a uno spread da 40.
3. **Walk-forward**, non un unico fit sull'intero periodo.
4. **Lista chiusa dei parametri variabili, dichiarata prima.** Ogni knob non dichiarato è
   sovra-adattamento.
5. **Fonte prezzi unificata su Alpaca** (§7).
6. **Nessun ordine reale, nemmeno in paper.**
7. Confronto contro almeno un baseline banale (buy-and-hold dell'universo): senza, uno
   Sharpe positivo non dice niente.

Nota sul disegno di S4 da tenere presente: S4 è dichiaratamente **tattico**
(`max_signal_age_hours: 4`, `rebalance_frequency: DAILY`), e il live conferma — 0,7 giorni
di detenzione mediana, 304 uscite su 362 sono `portfolio_sell`, cioè il ribilanciatore,
non il segnale. Se la simulazione mostrasse che l'informazione vive a 21-63 sedute, il
risultato riguarda **la scelta di orizzonte**, non la notizia.

## Cosa questo lavoro NON autorizza

- Nessuna modifica al path dei segnali. Filtro timing e scoring pre-apertura restano
  taratura: sono #607, e il freeze #171 regge fino al 28/09.
- Nessuna conclusione tratta dentro la issue: **l'output è il dato**.
- Non decide il 28/09 da solo. Al tavolo arriva **H-A**, se è pronta.

## Registro delle rotture del sigillo

Nessuna. Ogni modifica a questo documento dopo il primo download va aggiunta qui con data,
motivo e impatto sugli artefatti già prodotti.

| Data | Cosa è cambiato | Motivo | Artefatti invalidati |
|------|-----------------|--------|----------------------|
| 2026-09-17 | §1 distingue finestra di **popolazione** (`created_at`) da finestra di **paginazione** (`updated_at`, fino alla data di scaricamento); aggiunta §1.3 | Sonda contro l'API vera: `start`/`end` filtrano su `updated_at`. La versione precedente diceva solo «finestra 2024-2025», che su questa API significa una popolazione diversa da quella intesa | **Nessuno**: la sonda precede il primo scaricamento e nessuna misura era stata prodotta |
| 2026-09-18 | Lo script `scripts/coverage_news_archive_610.py` ora (a) costruisce il `body` via `AlpacaNewsConnector._parse_article` (HTML strip + collasso spazi, fallback summary), e (b) usa la chiave di dedup di produzione `(compute_dedup_hash(item), item.asset_tags[0])` invece del solo hash | Review di PR #620 (glm53, 2026-09-17): la prima versione riapplicava due regole di produzione — la normalizzazione del body e la composizione della chiave di dedup — con risultato divergente in entrambe le direzioni su `duplicato_produzione` e `ricostruita`. Regola #169/#467: il measurement deve chiamare la regola di produzione, non reimplementarla | I conteggi `duplicato_produzione` e `ricostruita` in `docs/evidence/copertura_news_610.json` (commit `77cc3e1`) **ereditano la vecchia regola**: vanno rigenerati prima di qualunque misura di Fase 1 che li usi come substrato. Da registrare anche in `OBSERVATION_CHARTER.md` come discontinuità di misura. Nessun esito pubblicato finora, quindi la finestra non è ancora inquieta |
