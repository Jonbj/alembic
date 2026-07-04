# S7 Revival Month — Decision Report (2026-07-04)

**Scope reale eseguito:** solo POC-1. Il PO ha acquistato FMP **Starter** ($29/mo), non
**Ultimate** ($99/mo) — il piano prevedeva Starter come sufficiente per entrambi i POC,
ma i transcript earnings (necessari a POC-2) sono gated su Ultimate, non su Starter
(verificato in Task 1: `earning-call-transcript` → `"Restricted Endpoint"`). Il PO ha
deciso di procedere solo con POC-1 (2026-07-04) piuttosto che effettuare l'upgrade.

## Esito sintetico

| POC | Gate | Esito | Numero chiave |
|---|---|---|---|
| POC-1 small/mid PEAD | net drift ≥+1.5%, hit>55%, n≥30 | **INCONCLUSIVE_DATA** | n=15 (7 BEAT + 8 MISS) su un minimo di 30 |
| POC-2 transcript tone (ALPHA-A3) | IC≥0.10, spread terzili ≥1.5%, split-half | **NOT EXECUTED** | Ultimate FMP richiesto ($99/mo), non acquistato |

## POC-1 — dettaglio

Report completo: `reports/s7_poc/POC1_smallmid_report_2026-07-04.md`. Sintesi:

- **Parametri:** finestra 2026-01-01/2026-05-15, |surprise|≥5%, cap $300M–$10B, ADV20g≥$5M, benchmark IWM, costo 30bps, hold 20 sedute.
- **Due bug di codice trovati e corretti in esecuzione** (dettagli nel report POC-1): (1) mismatch di unità nel market cap (`_market_caps` USD grezzi vs `classify_cap` in milioni — bucket small/mid sempre vuoto senza fix), (2) crash di batch Alpaca su ticker preferred (`ABR-PD` ecc.) che azzerava ~100 simboli buoni per ogni ticker invalido nel batch. Nessuno dei due fix ha toccato le soglie del gate pre-registrato.
- **Funnel:** 8.440 eventi con surprise rilevante → 6.177 simboli unici totali → 600 campionati (budget Starter, ordine alfabetico) → 442 eventi small/mid common-equity (314 simboli, 16 preferred esclusi) → **15 sopravvissuti** a barre IEX + liquidità (141 senza barre, 286 illiquidi <$5M ADV).
- **Risultato (n insufficiente per un verdetto):** BEAT n=7, mean netto −0.56% (mediana +1.02%), hit netto 57%; MISS n=8, mean netto −2.18% (mediana −4.53%), hit netto 50%.
- **Onestà sulla copertura:** i 15 eventi sopravvissuti hanno market cap $3.78B–$9.9B — nessuna vera small-cap (<$2B) è passata attraverso il filtro barre+liquidità. Il campionamento alfabetico dei primi 600 simboli (su 6.177) introduce inoltre un bias di selezione non misurato.

## POC-2 — dettaglio

**Non eseguito.** Task 1 (probe vendor) ha verificato che `/stable/earning-call-transcript`
risponde `"Restricted Endpoint: This endpoint is not available under your current
subscription"` con la chiave FMP Starter attiva. Ricerca esterna (site.financialmodelingprep.com/pricing-plans,
2026-07-04) conferma: i transcript sono inclusi solo nel piano **Ultimate**, non in Starter
né Premium. Costo Ultimate: **$99/mo** (verificato dal PO). Nessun dato POC-2 raccolto —
0 transcript scaricati, 0 tone score, nessuna IC calcolata. Task 4–6 del piano
(`fetch_s7_transcripts.py`, `score_s7_transcripts.py`, `analyze_s7_tone.py`) non sono
stati scritti né eseguiti: non avrebbe senso implementarli senza poter mai popolare la cache
transcript con la subscription corrente.

**Nota collaterale emersa durante il probe (non parte del gate, segnalata al PO in sessione):**
lo Starter attuale sblocca comunque due cose fuori scope di questo piano ma rilevanti per la
roadmap: (a) `earnings-calendar` include già `epsActual`/`epsEstimated` — il consensus per
ALPHA-A2, oggi estratto (rotto) dall'8-K nel `pead_worker` live; (b) `/grades`,
`/grades-historical`, `/price-target-summary` (ALPHA-D1, revisions) sono accessibili e
testati funzionanti. Nessuna azione presa su questi punti in questo piano — sono
opportunità di backlog, non parte del gate S7.

## Costi consuntivi

| Voce | Costo |
|---|---|
| FMP Starter (mese corrente) | $29 |
| LLM (Ollama) | $0 — POC-2 non eseguito, nessuna chiamata |
| Tempo — probe + debug + POC-1 (3 run + 1 diagnostico) | ~1h coding/debug + ~15 min runtime cumulato |

## Raccomandazione al PO (binaria dove possibile)

Nessuno dei due POC ha raggiunto un verdetto conclusivo (PASS o FAIL) — la matrice di
decisione pre-registrata ("entrambi FAIL → rimozione", "almeno un PASS → build") **non si
applica**: siamo nel caso non enumerato esplicitamente "INCONCLUSIVE_DATA / NOT EXECUTED su
entrambi". Non è possibile in coscienza raccomandare la rimozione definitiva di S7 su questa
base — significherebbe scartare un'ipotesi mai davvero testata, non un'ipotesi confutata.

Tre percorsi concreti, con costo:

1. **Espandere POC-1 senza spesa vendor aggiuntiva.** Il collo di bottiglia non è il vendor
   (Starter già copre `from`/`to` illimitato entro 300 call/min) ma il campione: 600 simboli
   alfabetici su 6.177 totali. Ampliare il campionamento di market-cap lookup (es. tutti i
   6.177, o un campione casuale stratificato) richiede solo più runtime (~10x, stimabile
   30-60 min), zero costo aggiuntivo. Non garantisce n≥30 (il vero limite è la copertura
   IEX/liquidità sui small-cap), ma è l'azione più economica per provare a chiudere POC-1.
2. **Upgrade a FMP Ultimate ($99/mo) per eseguire POC-2.** Sblocca i transcript e completa
   la parte del piano mai testata (l'edge qualitativo dichiarato di S7 fin dall'inizio,
   ALPHA-A3). Costo aggiuntivo $99/mo, ricorrente finché attivo; disdicibile a POC concluso.
3. **Accettare lo stato SHELVED senza ulteriori investimenti** e rivalutare S7 solo se
   emergono nuovi dati (es. un vendor free/economico per i transcript, o un ampliamento
   naturale dell'universo monitorato per altri motivi).

Se il PO non autorizza (1) o (2) entro la deadline del **2026-08-01**, la raccomandazione
di default è mantenere S7 `research`/blocked in `strategy_lifecycle` (nessun cambiamento)
piuttosto che dichiarare rimozione: il piano non ha prodotto un FAIL su nessuna delle due
ipotesi, solo dati insufficienti per deciderle.

**Promemoria:** se la decisione finale è la rimozione di S7, disdire FMP Starter prima del
rinnovo mensile (si tratta comunque della verifica in corso — Starter potrebbe essere
riutile per ALPHA-A2/D1, vedi nota POC-2 sopra, indipendentemente dalla sorte di S7).
