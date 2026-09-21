"""Lo score che il gate d'ingresso S4 valuta davvero (#550 / F-073).

Il ciclo S4 confronta `signals_df["score"]` con la soglia
`feedback:entry_threshold:S4` DOPO aver moltiplicato lo score grezzo del
segnale per il moltiplicatore di signal-velocity. Il punteggio che decide
l'ingresso e' quindi `grezzo x velocity`, non il grezzo: BA 2026-09-17 e'
stata comprata con grezzo 0.2738 < 0.300 perche' il gate ha visto 0.3285.

Chi misura «quali segnali passano il gate» con un'altra formula misura un
insieme diverso da quello che la produzione compra — la classe #169/#467.
La formula vive qui una volta sola: la produzione la chiama per costruire la
colonna che il gate confronta, le misure la chiamano sulle righe persistite
(`execution_decisions.signal_score` grezzo x `velocity_multiplier`).
"""
from __future__ import annotations


def deciding_entry_score(
    raw_score: float, velocity_multiplier: float | None
) -> float:
    """Punteggio valutato dal gate d'ingresso S4.

    Args:
        raw_score: score grezzo del segnale (polarity x confidence, com'e'
            persistito in `sentiment_signals.score`).
        velocity_multiplier: moltiplicatore di signal-velocity del simbolo in
            quel ciclo. None = non strumentato (righe pre-#550, o calcolo
            velocity non disponibile): si degrada a moltiplicatore unitario —
            mai a un gate implicitamente superato.
    """
    multiplier = 1.0 if velocity_multiplier is None else float(velocity_multiplier)
    return float(raw_score) * multiplier


def passes_entry_gate(
    raw_score: float,
    velocity_multiplier: float | None,
    threshold: float,
) -> bool:
    """True se il segnale supera il gate d'ingresso, com'e' confrontato in
    produzione: valore assoluto del decidente >= soglia (all'uguaglianza si
    resta dentro, i bearish sono gated come i bullish)."""
    return abs(deciding_entry_score(raw_score, velocity_multiplier)) >= threshold
