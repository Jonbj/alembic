-- Migration 077: velocity_multiplier su execution_decisions (#550 / F-073).
--
-- Il gate d'ingresso S4 confronta lo score DOPO il moltiplicatore di
-- signal-velocity, ma execution_decisions.signal_score riceveva il punteggio
-- grezzo (o quello trasformato, a seconda del path): nella seduta 2026-09-08
-- un SKIP_THRESHOLD a 0.2883 stava accanto a un BUY a 0.2663, e dal DB non
-- c'era modo di sapere perche'. La riga non si spiegava da sola.
--
-- Semantica dopo questa migrazione: signal_score e' SEMPRE il punteggio
-- grezzo del segnale (quello di sentiment_signals.score, quello che
-- l'analisi IC correla coi forward return); velocity_multiplier dichiara il
-- moltiplicatore applicato al gate in quel ciclo. Il punteggio effettivamente
-- valutato e' signal_score x velocity_multiplier (src/strategies/s4/
-- entry_gate.py, unica implementazione).
--
-- Nessun backfill: lo storico non registra il moltiplicatore per ciclo e
-- ricostruirlo inventerebbe un dato dentro una serie misurata. NULL =
-- «non strumentato» (righe pre-077, o cicli con calcolo velocity non
-- disponibile), ed e' un'informazione vera.
--
-- Freeze #171: strumentazione ed evidenza (etichetta freeze-ok). Nessuna
-- soglia, nessun peso, nessun comportamento d'ordine cambia.

ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS velocity_multiplier DOUBLE PRECISION;

COMMENT ON COLUMN execution_decisions.velocity_multiplier IS
    'Moltiplicatore signal-velocity applicato al gate d''ingresso S4 (#550): punteggio valutato = signal_score x velocity_multiplier, a confronto con la soglia attiva. NULL = non strumentato (righe pre-077 o velocity non disponibile), NON moltiplicatore unitario implicito.';
