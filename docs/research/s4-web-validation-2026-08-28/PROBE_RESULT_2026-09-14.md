# Esito del probe differenziale estrattore — 2026-09-14

Pre-registrazione: [PROBE_PREREG_2026-09-14.md](PROBE_PREREG_2026-09-14.md). Nessuna
scrittura in `node-output/`; la campagna sui due nodi non e' stata toccata.

## Risultato

| fonte | A — Q4_K_XL, ctx 8K, finestra 9.000 (6 chunk) | B — Q8_0, ctx 49K, finestra 30.000 (2 chunk) |
|---|---|---|
| MET005 | **12 validi**, 6 rifiutati — H18×8, H22×2, H07, H10 | **4 validi**, 2 rifiutati — H18×3, H22 |
| ACA010 | **12 validi**, 6 rifiutati — H19×6, H02×4, H05, H06, H07, H14, H21 | **4 validi**, 4 rifiutati — H19×2, H02, H06 |

**Nessuna ipotesi nuova in B. Nessuna delle ipotesi a zero (H16, H17) e' comparsa. B perde
due terzi del raccolto su entrambe le fonti.** A' non e' stato eseguito: la regola
pre-registrata lo subordinava a un esito positivo di B.

## Verdetto secondo la regola pre-registrata

`B ≤ A+2 su entrambe le fonti e nessuna ipotesi nuova` → **nessuna evidenza che lo
strumento sia il vincolo**. Nodo1 resta dov'e'; la finestra da 8K non e' cio' che tiene
vuoti H16 e H17.

## Perche' (ipotesi esplicativa, non pre-registrata)

Il raccolto per chiamata e' **circa costante (~2 claim) a prescindere dalla dimensione della
finestra**: 2,0 claim/chunk in A su 12 chunk, 2,0 claim/chiamata in B su 4 chiamate. Non e'
la finestra a limitare cosa il modello puo' vedere: e' il **numero di passaggi** a
determinare quanto raccoglie. Allargare la finestra riduce le chiamate e quindi il raccolto.

Conseguenza sul corpus esistente, da tenere presente quando si leggera' il consolidato: il
numero di claim per fonte misura soprattutto **in quanti pezzi la fonte e' stata letta**, non
quanto quella fonte ha da dire. IND001 ha 57 claim perche' e' stata spezzata in 59 chunk.

La tesi del "claim a cavallo del confine, strutturalmente irraggiungibile" e' **falsificata**
da questo probe: allargando la finestra fino a contenere i confini, quei claim non sono
emersi.

## Nota sui rifiuti

Tutti e 6 i rifiuti di B sono `INVALID_LINE_RANGE`, lo stesso modo di fallimento dominante
di nodo1 a Q4 (126 su 168). Il quant piu' alto non lo ha fatto sparire. n=6: indicativo, non
conclusivo.

## Velocita' (osservata, non oggetto del probe)

4 chiamate in 2.787s = **11,6 min per chiamata** su prompt da ~8K token, contro i ~22 min per
chunk osservati su nodo1 (che pero' include i retry). Circa 2×, che e' esattamente il
vantaggio gia' noto e gia' giudicato insufficiente a giustificare lo spostamento.

## Domanda ancora aperta

Perche' H16 e H17 sono a zero resta non spiegato. Il test piu' economico per deciderlo non e'
una finestra piu' larga ne' un quant migliore, ma **un passaggio mirato**: rileggere 2-3 fonti
chiedendo esplicitamente evidenza su H16/H17 e vedere se emerge qualcosa. Se non emerge
neanche chiedendo, "assente dalla letteratura del corpus" diventa una lettura difendibile.
