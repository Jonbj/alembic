# S1 — 02 Ipotesi scientifica / d'investimento

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04

## L'anomalia

S1 scommette sull'**anomalia del momentum** — l'evidenza empirica che i prezzi dei
titoli tendono a persistere nella loro direzione relativa su orizzonti di mesi:
i titoli che hanno sovraperformato (sottoperformato) continuano a sovraperformare
(sottoperformare) per un periodo successivo. È una delle anomalie più documentate
e robuste della finanza empirica, con due varianti distinte che S1 combina:

1. **Momentum cross-sectionale (Jegadeesh–Titman, 1993):** rankare i titori per
   rendimento passato e andare long i vincitori / short i perdenti produce rendimenti
   anomali non spiegati dal CAPM. S1 implementa esattamente questo lato long-only
   tramite lo **z-score cross-sectionale** ($S^{(i)}_t>0$ = sopra la media dei pari).

2. **Momentum time-series (Moskowitz–Ooi–Pedersen, 2012):** il segnale 12-1 (rendimento
   degli ultimi 12 mesi escluso l'ultimo mese) predice positivamente il rendimento
   futuro di un'attività rispetto a sé stessa. S1 include lookback 252d (≈12m) ma
   **non esclude l'ultimo mese** (nessuna "skip-month") e aggiunge 21/63/126d.

> La combinazione fa di S1 un ibrido TS/CS, non il TSMOM canonico. Le citazioni
> complete e la valutazione critica (repliche, decadimento post-pubblicazione,
> costi, capacità) sono in `03_literature.md`.

## Claim economico: perché dovrebbe essere "prezzato" (cioè perché dovrebbe esistere)

Due famiglie di spiegazioni, che l'audit deve tenere distinte (una è alpha, l'altra
è beta/compensazione):

- **Spiegazioni comportamentali (→ alpha genuino se vero):** underreaction dei
  investitori a informazioni graduali (Hong–Stein), anchoring/disposition effect
  (vendi troppo presto i vincitori, tieni i perdenti), delayed overreaction +
  reversal ( momentum come fase di un ciclo di overshooting). In questa lettura il
  momentum esiste perché gli agenti aggiornano i prezzi lentamente, e un trader
  sistematico può monetizzare il ritardo.

- **Spiegazioni risk-based (→ beta/compensazione, NON alpha):** il momentum carica
  fattori di rischio (es. esposizione a beta condizionale, momentum come proxy di
  qualità/crescita, cointegrazione con il fattore valore nel lungo periodo). In
  questa lettura il "rendimento anomalo" è compensazione per un rischio, non alpha
  arbitrabile.

## Come S1 operazionalizza l'ipotesi

- **Segnale multi-orizzonte con pesi esponenziali verso il lungo:** $w_l \propto e^{\mathrm{rank}(l)}$
  ⇒ il lookback 252d pesa ~20× il 21d. L'ipotesi implicita è che il momentum a 12m
  sia il segnale più informativo, con i lookback corti come conferma/tilt.
  **Tensione con la letteratura:** JT-1993 usa un'unica finestra di formazione
  (12m, o 3-12m) e **esclude l'ultimo mese** per evitare il reversal a breve
  (reversal 1m / effetto junction). S1 **non esclude l'ultimo mese** né filtra il
  reversal short-term — il peso del 21d (piccolo ma non nullo) espone al reversal
  di breve. La memoria di progetto (`MEMORY.md`: "skip-month = folklore") ha già
  discusso se lo skip-month sia necessario qui; l'audit verificherà.

- **Vol-normalizzazione del segnale:** divide il rendimento per la vol realizzata.
  Ipotesi: uniformare il "informativeness" del segnale across titoli a volatilità
  diversa (un +5% per un titolo a vol 10% è più informativo che per uno a vol 40%).
  Questo è un'ortogonalizzazione che la letteratura momentum canonica **non** fa
  (JT usa il rendimento grezzo). È una modifica proprietaria — da valutare in 03/04.

- **Z-score cross-sectionale + soglia 0:** long i titoli sopra la media dei pari.
  Ipotesi: il momentum è un fenomeno **relativo** (rank-based), non assoluto. In
  un mercato dove tutto sale, prendere long-only i vincitori relativi = beta
  possibile invece di alpha. La long-onlyità rimuove la gamba short che nel TSMOM
  canonico neutralizza il beta di mercato — ⇒ **S1 è strutturalmente esposto al
  beta di mercato** (long-only in un rialzo = beta positivo). La memoria di
  progetto lo conferma: "il momentum long-short è morto ma il crollo è sulla gamba
  short che non tradiamo" (`MEMORY.md`, osservazione 2026-08-01).

- **Sizing inverso-vol con target_vol 0.10:** ipotesi di risk-parity naive — ogni
  posizione contribuisce ~target_vol al rischio della sleeve. Non c'è scaling per
  **strength** del segnale (gate binario, vedi `01_specification.md` §3) — un titolo
  con z=0.01 e uno con z=3.0 ricevono lo stesso peso raw. Questo **devia** dalla
  letteratura momentum (dove lo strength del segnale scala tipicamente l'esposizione)
  e riduce il carry informativo del segnale alla pura direzione.

## Esposizione a alternative-beta (ante-letteratura, da verificare in 03/04)

A priori, S1 carica plausibilmente:
- **Beta di mercato** (long-only, no short leg) — quasi sicuramente.
- **Fattore momentum** (esiste come fattore stile; Carhart 1997) — per costruzione.
- **Low-volatility tilt** indiretto (sizing inverso-vol sovrappesa titoli a bassa vol)
  — possibile beta di bassa volatilità.
- **Quality/growth** indiretto (i vincitori recenti tendono ad avere momentum di
  utili) — da decompore.

Il verdetto `GENUINE_NET_ALPHA` vs `LIKELY_BETA` è rinviato a `04_alpha_assessment`,
alimentato dalla `03_literature.md`.

## Claim di progetto su S1

`config/strategies.yaml` (S1) dichiara il backtest **invalido** (demoted 2026-06-19):
same-bar fill (t+0, lookahead di fill), survivorship bias, assunzione zero-cost,
stress/regime circolare (hindsight), walk-forward "decorativo", DSR n_trials=1,
no live stop-loss. L'ipotesi momentum **non è stata validata** con un backtest
affidabile nel progetto — S1 è in `supervised_paper` per osservazione, non per
evidenza. Questo è il punto di partenza per 03/04: l'anomalia è robusta nella
letteratura, **ma l'istanza di Alembic non ha ancora dimostrato di catturarla
netta di costi**.

---
**Stato fase:** 02_hypothesis = **done**. Prossimo cursore: `S1:03_literature`.