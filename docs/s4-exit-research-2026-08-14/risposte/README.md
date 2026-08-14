# Risposte dei modelli

Le quattro risposte integrali raccolte per il consolidamento sono:

- `codex_analisi_exit_s4_2026-08-14.md`
- `glm52_analisi_exit_s4_2026-08-14.md`
- `opus_analisi_exit_s4_2026-08-14.md`
- `qwen35_analisi_exit_s4_2026-08-14.md`

Le risposte sono conservate come ricevute. Il confronto critico è in
`../consolidato_exit.md`; l'audit tecnico aggiornato è in
`../analisi_fattibilita_exit.md`.

## Errata non distruttiva

Le risposte attribuite ai modelli non vengono riscritte. La review indipendente
ha rilevato due errori fattuali nella risposta GLM-5.2:

- alla riga 65 si afferma che le posizioni fractionable non ricevono SL broker;
  in realtà `ALPACA_FRACTIONAL_STOP_ENABLED` abilita uno stop GTC sulla parte
  intera della posizione, lasciando scoperto soltanto il residuo frazionario
  (`src/config.py:230-236`;
  `src/portfolio/fractional_stop_orders.py:62-99`);
- alla riga 375 `src/strategies/s4/stop_policy.py` è un path inesistente; il
  file corretto è `src/portfolio/stop_policy.py`.

Il consolidato e l'analisi di fattibilità usano il comportamento e il path
corretti.
