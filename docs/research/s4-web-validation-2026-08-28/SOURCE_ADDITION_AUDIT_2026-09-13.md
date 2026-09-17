# S4 source-addition audit — 2026-09-13

## Esito

Raccomando un lotto aggiuntivo **minimo di due fonti**, con nuovi ID
versionati: `MET007` per la replica forward untouched (`H12`) e `ACA014` per
qualificare la gamba negativa e i moderatori dell'underreaction (`H17`, `H22`).
Entrambe sono copie full-text direttamente scaricabili da siti first-party degli
autori e non duplicano un'identita bibliografica gia presente nei manifest.

La raccomandazione e deliberatamente limitata. Non aggiungerei fonti MLOps
generiche per `H11` o `H16`: versionamento dello score, lane as-produced/frozen
e first pipeline loss cause esclusiva sono soprattutto contratti interni S4. La
letteratura generica su model cards, monitoring o observability sarebbe troppo
indiretta per verificare quelle formulazioni.

Questa verifica non modifica manifest, cache, ledger o campagne del cluster.

## Base della decisione

Nel corrente output v4, prima dei risultati di `ACA012` e `ACA013`, non esistono
claim per `H12`, `H15`, `H16` e `H17`; `H11` ha un solo claim. Il precedente
[source-gap audit](SOURCE_GAP_AUDIT_2026-09-10.md) associa `ACA012` soprattutto
a `H02`, `H06`, `H09`, `H20`, `H21` e `H22`, e `ACA013` a `H01`, `H15`, `H19`
e `H21`. Di conseguenza, anche dopo quel lotto, i gap literature-addressable
attesi restano `H12` e, con una qualificazione importante, `H17`.

Le associazioni fonte-ipotesi sotto sono inferenze di preselezione. Diventano
evidenza soltanto dopo il normale passaggio evidence-bound node1 -> node2.

## `MET007` — Arnott, Harvey e Markowitz

- **Titolo/versione congelata:** Rob Arnott, Campbell R. Harvey e Harry
  Markowitz, *A Backtesting Protocol in the Era of Machine Learning*, versione
  29 ottobre 2018, 18 pagine. Il frontespizio identifica autori, affiliazioni,
  titolo e versione. Il [record Duke Scholars](https://scholars.duke.edu/publication/1518184)
  collega la stessa opera alla pubblicazione nel *Journal of Financial Data
  Science* 1(1), 64-74 (2019), DOI
  [`10.3905/jfds.2019.1.064`](https://doi.org/10.3905/jfds.2019.1.064).
- **Full text first-party:** [PDF ospitato dal corresponding author alla Duke University](https://people.duke.edu/~charvey/Research/Published_Papers/SSRN-id3275654.pdf).
  Verificato scaricabile come PDF non cifrato.
- **Byte verificati:** 291.336 byte; SHA-256
  `2ebced0662e2ced12d8ab28297e1f7a97bda597d350ca86b774f5de7a3ba4144`.
- **Copertura attesa:** copre direttamente `H12`. Il paper distingue il normale
  holdout storico dal vero out-of-sample live, avverte che modificare il modello
  dopo aver osservato il holdout lo rende parte dell'overfitting e propone un
  protocollo di ricerca per ridurre falsi positivi. Questo e precisamente il
  motivo per cui il backfill S4 va trattato come discovery e la promotion deve
  dipendere da una replica forward untouched.
- **Copertura secondaria:** puo qualificare `H11` e `H13` per disciplina delle
  modifiche live e controllo del research process, ma non prova da solo che le
  due lane S4 debbano avere l'esatta struttura as-produced/frozen.
- **Limite:** il candidato e il manoscritto d'autore 2018, non la Version of
  Record 2019; versione e hash devono quindi restare espliciti.

## `ACA014` — Hong, Lim e Stein

- **Titolo/versione congelata:** Harrison Hong, Terence Lim e Jeremy C. Stein,
  *Bad News Travels Slowly: Size, Analyst Coverage, and the Profitability of
  Momentum Strategies*, prima bozza marzo 1998, versione gennaio 1999, 10
  pagine. Il frontespizio del PDF riporta titolo, autori e data. Il
  [record NBER del Working Paper 6553](https://www.nber.org/papers/w6553)
  conferma identita e autori e registra la successiva pubblicazione nel
  *Journal of Finance* 55(1), 265-295 (2000).
- **Full text first-party:** [PDF ospitato sul sito MIT dell'autore Jeremy Stein](https://www.mit.edu/~jcstein/badnews.pdf).
  Verificato scaricabile e text-readable.
- **Byte verificati:** 138.334 byte; SHA-256
  `c0095f45648b2afe201338a3a22b7ef2649e2912ded2c3d587d639c58b7e8591`.
- **Copertura attesa:** qualifica `H17` e supporta `H22`; e rilevante anche per
  `H03`. Il disegno trova che l'effetto della bassa analyst coverage sul
  momentum e piu forte per past losers che per past winners e interpreta il
  risultato come diffusione particolarmente lenta dell'informazione negativa.
  Fornisce quindi una base empirica per conservare la gamba negativa come
  informazione distinta invece di riclassificarla come "missed long".
- **Limite sostanziale:** il segnale e past return/momentum, non sentiment di
  una singola news; il paper valuta strategie long-short e non dimostra la
  specifica policy S4 veto/shadow-short. Per `H17` il verdetto corretto atteso e
  dunque `QUALIFIES`, non una convalida piena.
- **Limite di versione:** e una bozza d'autore gennaio 1999, non la Version of
  Record 2000; non va presentata come tale.

## Righe TSV proposte

Da aggiungere al manifest di recupero/estensione, senza alterare gli ID
congelati esistenti:

```tsv
MET007	method	pdf	https://people.duke.edu/~charvey/Research/Published_Papers/SSRN-id3275654.pdf	A Backtesting Protocol in the Era of Machine Learning — author manuscript, version 29 October 2018
ACA014	academic	pdf	https://www.mit.edu/~jcstein/badnews.pdf	Bad News Travels Slowly — author draft, January 1999
```

## Fonti non aggiunte

- **Nessuna fonte nuova per `H15`:** `ACA013` e gia stata scelta appositamente
  per annotazione umana, accordo e confronto con baseline lessicale. Valutarne
  prima le review evita una duplicazione prematura.
- **Nessuna fonte nuova per `H09`:** `ACA012` tratta news neutrali e non-news,
  mentre `ACA011` ha gia prodotto un claim pertinente. Il requisito specifico
  matched no-news resta una scelta di disegno da verificare nel consolidato.
- **Nessuna fonte MLOps per `H11`/`H16`:** observability e model governance
  generiche non stabiliscono ne la semantica delle lane di score S4 ne
  l'esclusivita della first loss cause. Qui servono soprattutto ledger,
  reason-code e test della pipeline Alembic.

## Raccomandazione operativa

Accodare soltanto `MET007` e `ACA014` dopo il completamento integro di
`ACA012`/`ACA013`. Conservare i file con gli hash sopra e richiedere per entrambi
il normale ciclo node1-node2; non usare il titolo della pubblicazione finale per
nascondere che le copie ingerite sono manoscritti d'autore datati.
