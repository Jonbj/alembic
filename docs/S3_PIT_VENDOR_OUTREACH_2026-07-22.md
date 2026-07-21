# S3 PIT vendor outreach — 2026-07-22

## Scopo e limite operativo

Questa nota prepara una richiesta commerciale **senza inviarla**. La verifica usa
soltanto pagine ufficiali CRSP/Morningstar, Nasdaq Data Link e Sharadar consultate
il 22 luglio 2026. Non sono stati inviati moduli o email, creati account, aperti
trial o autorizzati acquisti.

## CRSP / Morningstar

- **Canale consigliato:** il
  [CRSP Subscription Information Request](https://www.crsp.org/subscription-information/).
  La pagina CRSP di contatto indica espressamente questo modulo per subscription
  e licensing e pubblica anche l'indirizzo diretto
  `crsp-subscriptions@morningstar.com` per le richieste commerciali
  ([fonte ufficiale](https://www.crsp.org/contact-us/)).
- **Prodotto da selezionare:** `CRSP Research Data Products`, quindi
  `CRSP US Stock Databases`. Non selezionare `CRSP Market Indexes`: la richiesta
  riguarda security-level research data, non un indice o un benchmark.
- **Campi d'identità mostrati dal modulo:** First Name, Last Name, Institution,
  Title/Position, Phone ed Email Address. Solo `Institution` è marcato
  esplicitamente “required” nel testo pubblico del modulo; non va dedotta
  l'obbligatorietà degli altri campi senza convalidare il form nel browser.
- **Altri campi:** product(s) of interest, descrizione breve dell'intended use
  case (`Your Message`) e `How'd you hear about us?`, con eventuale campo libero
  quando si seleziona Other. Il modulo non espone un campo Subject separato.
- **Oggetto consigliato per l'email:**
  `Pre-purchase qualification — CRSP US Stock Database snapshot, 1998–2025`.
- **Vincolo dichiarato dal vendor:** CRSP presenta i database come prodotti per
  licensee presso istituzioni accademiche, agenzie governative e investment
  practitioners e rimanda altrove gli individual investors
  ([subscription page](https://www.crsp.org/subscription-information/)). Il
  richiedente deve quindi identificare correttamente l'entità e il caso d'uso;
  non va descritta Alembic come istituzione se non lo è.
- **Transizione:** CRSP dichiara che Morningstar ha completato l'acquisizione il
  2 febbraio 2026 e che il contenuto CRSP.org migrerà al sito Morningstar Indexes
  dal 28 luglio 2026. Per questo documento fanno fede il form CRSP corrente e
  l'email Morningstar pubblicata nella pagina di contatto.

## Nasdaq Data Link / Sharadar

- **Canale consigliato:** email a `datasales@nasdaq.com`. Nasdaq pubblica questo
  indirizzo per il supporto commerciale sui prodotti dati
  ([fonte ufficiale](https://www.nasdaq.com/solutions/nasdaq-basic)); il portale
  Data Link indica inoltre che i prodotti istituzionali richiedono il contatto
  con data sales
  ([fonte ufficiale](https://data.nasdaq.com/about)).
- **Canale form alternativo:** la pagina ufficiale
  [Nasdaq Data Link APIs](https://www.nasdaq.com/solutions/data/nasdaq-data-link/api)
  invita a usare `Contact Us` per trial o subscription e rimanda al
  [landing form Nasdaq](https://nd.nasdaq.com/GDPLP25-02-10Global-Web-Contact-Us37026.html).
  Il form è reso esclusivamente via JavaScript; il fallback ufficiale consultato
  non elenca i campi e mostra testo segnaposto. Di conseguenza non esiste, nella
  pagina statica verificabile, un elenco autorevole dei campi obbligatori. Non
  compilare il form finché i campi non sono verificati interattivamente; l'email
  sales evita questa ambiguità e non impone campi strutturati.
- **Prodotto da indicare:** `Sharadar` su `Nasdaq Data Link`, chiedendo al sales
  team di quotare il singolo bundle minimo che includa daily US equity prices,
  active e delisted securities, historical ticker/security metadata, corporate
  actions e `Sharadar Core Fundamentals (SF1)`. `Sharadar Core Fundamentals` e
  il codice `SF1` sono nomi ufficiali correnti
  ([Nasdaq Data Link documentation](https://docs.data.nasdaq.com/docs/data-organization));
  Sharadar conferma che daily stock prices sono complementari ai fundamentals e
  che esiste preferential pricing per più dataset tramite bundle
  ([Sharadar data page](https://www.sharadar.com/data)). Non assumere un nome o
  un prezzo corrente per il bundle: deve essere il vendor a identificare
  nell'offerta tutti i dataset e le tabelle necessarie.
- **Oggetto consigliato:**
  `Pre-purchase qualification — Sharadar PIT US equities bundle, 1998–2025`.
- **Vincolo:** la pagina publisher è JavaScript-gated e non pubblica uno schema
  commerciale completo
  ([publisher ufficiale](https://data.nasdaq.com/publishers/SHARADAR)). Non è
  richiesto creare un account per inviare l'email sales; qualsiasi sample o trial
  resta da autorizzare separatamente dopo la risposta.

## Messaggio vendor-neutral pronto da inviare

Usare lo stesso corpo per entrambi i vendor, sostituendo soltanto `[Vendor]`,
`[Product]` e i dati reali del mittente. Le risposte richieste devono essere
scritte; non costituiscono un ordine.

```text
Subject: Pre-purchase qualification — PIT US equities snapshot, 1998–2025

Hello [Vendor] Data Sales,

I am evaluating [Product] for a small, internal, non-production proof of concept.
No order is being placed with this message. Before requesting purchase approval,
please provide a written answer to every item below and identify the exact product,
tables and licence that your proposed quote covers.

1. Can you provide a single 1998–2025 snapshot for a total initial cost of no
   more than EUR 1,000, including VAT and all fees?
2. Can the order have a fixed term with no automatic renewal and no advance
   cancellation or non-renewal notice requirement?
3. May we download and retain the snapshot locally for internal reproduction of
   this proof of concept, including storing release provenance and our own file
   checksums?
4. Does the snapshot contain daily close and volume, and, where available, a
   reliable official open, for both active and inactive securities?
5. Does it contain historical market capitalization or shares outstanding with
   an available-at or filing timestamp sufficient to calculate market cap without
   look-ahead bias at every month-end from 1998 through 2025?
6. Does it contain historical validity intervals for security type, share type
   and primary exchange, sufficient to select US-primary-listed common shares and
   exclude ETFs, ADRs, preferred shares, funds and OTC securities point in time?
7. Does it contain splits, cash and special dividends, mergers, ticker changes
   and a stable security identifier across those events?
8. Does it contain delisting date, last trade and the post-delisting economic
   payout or return, with an explicit missing-status flag when that value is not
   known?
9. Can you provide a schema and sample records for at least one
   bankruptcy/worthless case, one cash acquisition and one exchange migration to
   OTC?
10. Can you provide the monthly eligible-security counts for 1998–2025 after
    applying price >= USD 5, point-in-time market cap >= USD 2 billion, trailing
    60-session ADV >= USD 10 million and at least 252 prior trading sessions; or
    grant a trial that explicitly permits us to calculate those counts?

For item 10, the proof of concept requires at least 200 eligible securities at
every primary month-end rebalance. Please also state the earliest available date
for every quoted table, the delivery format, release/version identifier, quote
expiry date, and any restrictions on local retention after the licence term.

Please attach or link the applicable licence terms and a sample schema. A
qualified response must cover all items 1–8 in one vendor offering; we cannot
combine products from different vendors.

Organisation/legal entity: [truthful legal name or “individual developer”]
Intended use: internal, non-production research proof of concept; no redistribution
Country: Italy

Kind regards,
[Name]
[Role]
[Email]
[Phone, if desired]
```

## Invio manuale consigliato

1. CRSP: usare il form con `CRSP Research Data Products` →
   `CRSP US Stock Databases`; se il testo supera il limite del form, inviare
   l'email completa a `crsp-subscriptions@morningstar.com` e usare il modulo solo
   per richiedere la presa in carico.
2. Nasdaq: inviare direttamente a `datasales@nasdaq.com`, nominando Sharadar nel
   subject e nella prima riga. Chiedere che la risposta specifichi il nome
   commerciale corrente del bundle e ogni dataset/tabella incluso.
3. Non accettare trial, termini o offerte e non fornire dati di pagamento durante
   questo contatto. Conservare le risposte scritte come evidenza per rieseguire il
   gate dati della issue #84.
