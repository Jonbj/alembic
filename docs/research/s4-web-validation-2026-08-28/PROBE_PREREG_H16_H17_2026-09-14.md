# Pre-registrazione — passaggio mirato H16/H17, 2026-09-14

Scritta prima di eseguire. Seguito di [PROBE_RESULT_2026-09-14.md](PROBE_RESULT_2026-09-14.md),
che ha stabilito che il raccolto dipende dal **numero di passaggi**, non dalla finestra.

## Domanda

H16 e H17 hanno **zero claim** nel consolidato v4. E' perche' il corpus non ne parla, o perche'
il passaggio generico — che raccoglie ~2 claim per chiamata, quelli piu' salienti — non ha mai
chiesto di quelle due?

## Intervento (una sola variabile)

Identica pipeline di produzione (`node1_prompt`, `node1_response_format`, `validate_card`,
`temperature 0.0`, `top_p 0.9`, `enable_thinking: False`, finestra **9.000/500**,
`max_tokens 1200`). **Cambia solo il registro passato al prompt**: contiene esclusivamente

- **H16** — Una first pipeline loss cause esclusiva rende il capture gap diagnosticabile.
- **H17** — La gamba negativa e' informativa/veto/shadow-short, non missed long su ticker non
  detenuto.

Il modello e' quindi Q8_0 locale invece di Q4 su nodo1: confondente dichiarato, non isolabile
in questo giro.

## Campione (fissato ora)

Entrambe le fonti vengono lavorate **integralmente**, a prescindere dall'esito della prima.

1. **ACA014** — *Bad News Travels Slowly* (Hong, Lim, Stein; draft MIT), 89.208 char, 11 chunk.
   Scelta perche' il [SOURCE_ADDITION_AUDIT del 2026-09-13](SOURCE_ADDITION_AUDIT_2026-09-13.md)
   l'ha aggiunta **espressamente per H17 e H22**, prima di questo probe. Nel passaggio generico
   ha prodotto 26 claim e **zero su H17**. E' il test piu' netto disponibile.
2. **ACA010** — *Sentiment Trading with Large Language Models*, 48.373 char, 6 chunk. Scelta
   perche' i lavori di questa classe riportano tipicamente la gamba long e quella short separate,
   cioe' esattamente il contenuto di H17. Nel passaggio generico: 12 claim, zero su H17.

## Esito primario

Numero di claim che superano `validate_card` con `hypotheses` contenente H17; idem per H16.

## Regola di decisione (fissata ora)

- **≥ 1 claim H17 valido** → il passaggio generico non trova cio' che non chiede. Gli zeri del
  consolidato sono un artefatto del prompt, non un fatto sulla letteratura, e nessuna ipotesi a
  zero puo' essere letta come "assente" senza un passaggio mirato.
- **0 claim H17 su entrambe** → per H17 "non trattata da questo corpus" diventa una lettura
  difendibile, avendo interrogato la fonte scelta apposta per quell'ipotesi.

**H16 e' asimmetrica e va dichiarato ora**: il [SOURCE_GAP_AUDIT del 2026-09-10](SOURCE_GAP_AUDIT_2026-09-10.md)
sostiene gia' che H16 e H11 sono **contratti interni S4**, non domande di letteratura. Da H16 mi
aspetto zero e uno zero **non e' informativo**: conferma l'audit. Un claim H16 valido sarebbe
invece una sorpresa da ispezionare a mano.

## Vincoli

Nessuna scrittura in `node-output/`, nessun `retry_campaign`, nessun contatto con la campagna in
corso sui due nodi. Una sola esecuzione per chunk: un singolo claim isolato va letto come pista,
non come prova.
