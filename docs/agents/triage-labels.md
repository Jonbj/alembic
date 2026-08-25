# Triage Labels

The skills speak in terms of five canonical triage roles, plus one local role this repo added. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |
| *(nessuno — locale)*       | `waiting`            | In attesa di una data o di un campione   |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## `waiting` — ruolo locale, aggiunto il 2026-08-25

I cinque ruoli canonici non hanno una casella per l'issue **pienamente specificata su cui non c'è
nulla da fare finché non arriva una data o non matura un campione**. Senza quella casella
`ready-for-human` finiva per fare da parcheggio, e la coda dell'operatore si gonfiava di ticket che
non chiedevano niente a nessuno: al momento dell'introduzione, 15 issue `ready-for-human` di cui
solo 6 richiedevano davvero una decisione.

Un'issue è `waiting` quando **si sblocca da sola**:

- aspetta una data (tipicamente la scadenza del freeze #171, 2026-09-28);
- aspetta che un campione shadow raggiunga una numerosità utile (#83, #85);
- aspetta un'altra issue aperta — in quel caso la dipendenza nativa `blocked_by` dice *su cosa*, e
  `waiting` dice solo *non è il tuo turno*.

Un'issue **non** è `waiting` se qualcuno deve fare qualcosa perché si sblocchi: quello è
`ready-for-agent` o `ready-for-human` a seconda di chi.

**Convenzione obbligatoria:** ogni issue `waiting` nomina la sua condizione di risveglio nel corpo o
nell'ultimo commento di decisione, come riga esplicita:

```
Revisione: 2026-09-28
```

oppure, quando la condizione è un campione e non una data, la soglia che la fa maturare. Una
`waiting` senza condizione di risveglio scritta è indistinguibile da una dimenticata — e va
ri-triagiata, non lasciata lì.

`waiting` è mutuamente esclusiva con `ready-for-agent` e `ready-for-human`.
