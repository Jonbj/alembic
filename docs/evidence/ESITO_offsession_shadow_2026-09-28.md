# Esito misura shadow off-session (Opzione C) — decisione Opzione D del 2026-09-28

Data di esecuzione: **2026-09-28** (freeze #171 scaduto). Origine:
`docs/evidence/PREREGISTRAZIONE_offsession_shadow_2026-09-10.md` — campione, regola,
criterio e perimetro fissati il 2026-09-10, **prima** del primo run. Nessuna parte
della regola è stata modificata dopo aver visto i dati; le uniche integrazioni
dopo i dati sono l'errata sul numero di migrazione (2026-09-11, già registrata)
e la compilazione di «Prima esecuzione» in questo documento.

## 1. Stato della piattaforma al momento della lettura

| Pezzo | Stato |
|---|---|
| B — misura stale-drop per coorte (`fix/stale-drop-coorte`) | **MERGIATA**, PR #560, 2026-09-12 13:52Z |
| A — censimento coda 24/7 (`feat/news-queue-census`) | **MERGIATA**, PR #561, 2026-09-12 08:14Z |
| C — shadow off-session (`feat/sentiment-offsession-shadow`) | **MERGIATA**, PR #562, 2026-09-12 13:43Z |
| Deploy C (beat `sentiment-shadow-offsession` attivo) | confermato: prima riga shadow 2026-09-12 22:15:16Z, ultima 2026-09-28 07:15:47Z; container `alembic-beat-1` riavviato 2026-09-27 14:20Z con il task nel beat |

Prima esecuzione con dati: **2026-09-12 22:15:16Z** (compilata a posteriori nella
pre-registrazione, riga «Prima esecuzione»).

## 2. Verifiche di falsificazione (§7 della pre-registrazione)

1. **Perimetro delle scritture — INTATTO.** Zero righe in `sentiment_signals` e
   `news_log` attribuibili allo shadow: le uniche righe fuori seduta in
   `sentiment_signals` sono 492, tutte di giugno-luglio 2026 (storia pre-deploy,
   nessuna dopo il deploy C); `news_log` fuori seduta solo giugno-luglio. Il
   worker shadow ha scritto **solo** su `sentiment_signals_offsession_shadow`,
   in due fasce: notte 00:00-12:15Z (1353 righe, beat `0-12`) e sera 22:15-23:15Z
   (617 righe, beat `22-23`). Zero righe nella finestra 13:30-20:59Z.
2. **La coda non viene consumata — CONFERMATO.** Il censimento (A) mostra la
   profondità di `news:queue` che cresce in modo **monotono** durante l'intera
   finestra shadow (es. 09-14: 188 item a mezzanotte → 405 alle 13:30Z, età
   massima che sale di 1h all'ora; 09-22: 29 → 303). Il crollo 405 → 89 a
   13:35Z con `n_stale → 0` è lo **scarto stale alla campanella** (il difetto
   stesso, misurato da B), non un consumo shadow.
3. **Tasso di fallback — PUBBLICATO (anomalo ma non estremo).** Nella stessa
   finestra 2026-09-12 → 2026-09-28: path live 834/2148 = **38,8%**; shadow
   976/1970 = **49,5%** (+10,7pp). Le notti del 12-13/09 (deploy) sono state
   **100% FinBERT** (94 righe su 94 il primo giorno, 94 su 94 il secondo): le
   prime due notti misurano la disponibilità notturna di Ollama Cloud, non il
   contenuto delle news. Dall'11/09 notturno in poi il fallback shadow è
   45-60%: la direzione dell'effetto (più fallback di notte che di giorno) è
   reale e va dichiarata in ogni lettura di questi punteggi.

## 3. Campione osservato (nessuna regola cambiata)

- **17 notti attive** (2026-09-12/13 → 2026-09-27/28), **1970 articoli** classificati, **zero** item con `published_at` NULL.
- **Tetto 200/notte mai raggiunto** (massimo 195 articoli/notte): la limitazione «campione = coorte più vecchia» **non si è mai materializzata**. Lo scadenza dura 13:15Z non ha mai troncato un lotto a metà (nessuna notte ha esaurito il tetto).
- **Unità di analisi** (simbolo, giorno UTC di `published_at`, |score| massimo): **1217**, ridotte da 1970 articoli.
- Fonte: **100% `alpaca_benzinga`** (non c'erano altre fonti in coda nelle notti osservate).
- Fallback (FinBERT) per unità: 711/1217 = 58,4%; per unità sopra gate: 70/125 = 56,0%.
- Distribuzione |score| delle unità sopra gate: media 0,420, mediana 0,390, p75 0,438, p90 0,544, max 0,900.

## 4. Risultato primario: n sopra gate

**n = 125 simbolo-giorni con |score| > 0,30** su tutta la finestra (125/1217 = 10,3%).

→ Il criterio pre-registrato `INSUFFICIENT_N se n < 30` **non si applica**: il
campione è sufficiente e la pre-registrazione impone di pubblicare l'intero
esito direzionale. Non è un esito che si può tacere.

Per notte: 09-12: 9, 09-14: 6, 09-15: 9, 09-16: 12, 09-17: 12, 09-18: 24,
09-19: 5, 09-21: 2, 09-22: 16, 09-23: 6, 09-24: 9, 09-25: 12, 09-26: 1,
09-27: 2 (notti 13, 20, 26, 28/09: zero).

## 5. Forward return D+1 (regola `compute_label_forward_returns.py`, barre Alpaca IEX daily, Adjustment.ALL, point-in-time da `published_at`, close-to-close 1ª→2ª barra ≥ published_at)

Replica della funzione `_forward_returns` del prodotto (barre daily, IEX,
`Adjustment.ALL`), eseguita nel container `alembic-worker-1` con le stesse
credenziali e lo stesso feed. **Zero scritture su DB**: i risultati vivono in un
checkpoint locale (`/tmp/shadow_fr_ckpt.json` nel container) e in questo documento.

| Gruppo | n | con FR D+1 | FR non disponibile | media | mediana | win rate |
|---|---|---|---|---|---|---|
| **sopra gate, score > 0** (long side) | 54 | 54 | 0 | **−0,011%** | +0,079% | 51,9% |
| **sopra gate, score < 0** (short side) | 44 | 44 | 0 | **+0,335%** | −0,185% | 40,9% |
| sopra gate totale | 125 | 98 | 27 | — | — | — |

- **27 unità sopra gate senza barre**: 22 sono simbolo-giorni pubblicati 27-28/09
  (D+1 non ancora completato alla data di questa lettura — non valutabili per
  costruzione, un pass di retry a run 2026-09-28 non ha recuperato nulla), 3 sono
  coppie crypto senza barre IEX (`SOL`/`SOLUSD`, `POLUSD`), le restanti sono
  gap IEX. Nessuna diventa zero (§3 prereg).
- Long side: media ≈ zero, mediana leggermente positiva. Short side: media
  positiva (+0,33%) contro il segno atteso, mediana quasi nulla — **nessuna
  direzione mostra il pattern atteso** (sopra-gate long che rende, sopra-gate
  short che perde).

### Correlazione score ↔ forward return (barra carta |t| ≥ 3)

| Popolazione | n | Pearson r | HAC t (Newey-West, 6 lags) |
|---|---|---|---|
| Tutte le unità con FR | 874 | **+0,005** | **+0,16** |
| Solo sopra gate | 98 | −0,051 | −0,51 |

Robusto alla scelta dei lags (3/6/12: t = +0,163 / +0,160 / +0,155).

**`ic_rilevabile_a_t3` = r 0,102** (n = 874; 0,308 sulla sotto-popolazione gate).
L'r osservato (+0,005) è un ordine di grandezza sotto la soglia di rilevabilità:
si legge **«non rilevabile»**, **mai** «assente» (§4 prereg).

## 6. Verdetto

| Criterio prereg | Esito |
|---|---|
| n ≥ 30 simbolo-giorni sopra gate | **PASSATO** (n = 125) — non è `INSUFFICIENT_N` |
| Forward return D+1 coerenti (segnati per direzione, t ≥ 3) | **NON SUPERATO**: t = +0,16 (tutte) / −0,51 (gate); long ≈ 0, short di segno opposto a quanto servirebbe alla D |

**La condizione per implementare la D (n ≥ 30 E forward return coerenti) NON è
soddisfatta. La D NON viene implementata oggi.**

Ciò **non** è `INSUFFICIENT_N` e **non** è «la coorte notturna non ha alpha»: la
coorte produce 125 segnali sopra gate in 17 notti — la materia prima **esiste**.
Ciò che non c'è, a questa potenza, è un **legame direzionale misurabile** fra lo
score notturno e il forward return D+1: la correlazione è zero a un ordine di
grandezza dalla soglia di rilevabilità, e le due code (long/short) non danno il
pattern che la D spreccherebbe (uscite più informate sui simboli detenuti).

## 7. Conseguenze registrate

1. **La D resta in roadmap post-freeze come opzione NON prioritaria**; la
   decisione è dell'operatore. L'argomento «il gate di seduta appartiene
   all'esecuzione» resta valido in astratto, ma oggi non ha evidenza che lo
   renda prioritario rispetto al resto della roadmap: il valore atteso della D
   (path uscite via esenzione #150) non è supportato dai dati raccolti.
2. **L'esenzione #150 e il gate d'ingresso non cambiano**: nessun parametro
   toccato (freeze scaduto, ma la prereg non dà il verde).
3. **Lo shadow off-session resta attivo** (perimetro invariato, zero scritture
   live): ogni notte aggiunge unità, e la correlazione è ricalcolabile a costi
   quasi nulli se l'operatore vuole rivedere la D con più campione. La finestra
   di questa misura resta quella registrata (fino al 28/09); eventuali letture
   successive sono **nuove misure**, non estensioni di questa.
4. La serie `stale_drop_metrics_daily` (Opzione B) resta il monitor del difetto
   di coda: la quota `went_stale_off_session` continua a essere pubblicata
   separatamente e la D non è urgente per igiene della coda (il censimento A
   mostra il dente di sega notturno ancora presente).

## 8. Limitazioni dichiarate

- **Fonte unica**: tutto il campione è `alpaca_benzinga`; la conclusione vale
  per la coorte notturna **di quella fonte**, non per la coda in generale.
- **Fallback notturno più alto** (49,5% vs 38,8% live; 100% nelle prime due
  notti): i punteggi FinBERT pesano più nello shadow che nel live. Le unità
  sopra gate con fallback sono il 56% (70/125).
- **Barre IEX** (non consolidated): il feed del prodotto è IEX, quindi la
  replica è fedele al prodotto; come misura del valore informativo può
  sottostimare i move. Il confronto col gap off-session pre-registrato (#606,
  barre IEX) resta coerente.
- **`published_at` del WebSocket** (≈ ingest, non event time del wire): stessa
  semantica del path live, scelta dichiarata in prereg §3.
- **Nessun controllo multipolicità tra le due letture (tutte/gate)**: sono
  riportate entrambe come richiesto, nessuna delle due supera la barra.

## 9. Provenienza operativa

- Letture DB: `psql` su `alembic-postgres-1` (sessione UTC), query in
  `/tmp/shadow_query.sql`, `/tmp/shadow_falsif.sql`, `/tmp/attrib_query.sql`,
  `/tmp/queue_check.sql`, `/tmp/census_detail.sql`, `/tmp/tz_check.sql`,
  `/tmp/nights.sql`, `/tmp/null_check.sql` (macchina dev 192.168.178.144).
- Forward return: replica di `scripts/compute_label_forward_returns.py::_forward_returns`
  (daily/IEX/ALL), script `/tmp/shadow_fr.py` + `/tmp/shadow_retry.py` +
  `/tmp/shadow_hac2.py` eseguiti in `docker exec alembic-worker-1`; checkpoint
  `/tmp/shadow_fr_ckpt.json` (1217 chiavi: 874 con FR, 343 NULL — di cui 27
  sopra gate), statistiche `/tmp/shadow_hac_final.json`.
- Le query non hanno scritto su alcuna tabella; gli script non hanno toccato
  `sentiment_signals`, `news_log` o Redis (il checkpoint vive nel `/tmp` del
  container worker, non nel volume dell'app).