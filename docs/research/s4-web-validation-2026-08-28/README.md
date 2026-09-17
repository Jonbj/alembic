# S4 deep web validation — local-cluster workspace

Stato: **ricerca in corso; nessuna modifica S4 autorizzata**  
Data di avvio: 2026-08-28

Protocollo attivo: **v4**. Le righe legacy, v2 e gli start interrotti v3 restano nel ledger per
audit, ma il consolidamento deve usare esclusivamente card e review con `protocol_version == 4`.

Questa directory contiene il lavoro di validazione/confutazione delle ipotesi del progetto
`S4 event evaluation`. Il corpus viene acquisito da fonti primarie o first-party. I due nodi locali
Qwen3.8 lavorano su testo congelato: non possono aggiungere fonti al corpus né promuovere claim non
supportati da un estratto verificabile.

## Ruoli

- node1, `qwen3.8-27b-implementer` Q4: lettura per chunk e produzione di source cards;
- node2, `qwen3.8-27b-reviewer` IQ3: critica compatta di claim ed evidence context;
- orchestratore: download, estrazione, chunking, verifica exact-substring, checkpoint e ledger;
  dopo la prima fonte mette in pipeline le review sul nodo 2 mentre il nodo 1 continua
  l'estrazione delle fonti successive;
- Codex: verifica finale dei riferimenti e consolidamento, non prima che i nodi abbiano completato
  il primo passaggio.

## Guardrail anti-allucinazione

1. Ogni claim deve citare un `source_id` del manifest.
2. Ogni claim deve includere una breve `evidence_quote` copiata esattamente dal testo fornito.
3. L'orchestratore scarta meccanicamente quote che non sono substring del chunk.
4. I follow-up bibliografici proposti dal modello restano `UNVERIFIED` e non diventano fonti.
5. `INSUFFICIENT`, `MIXED` e `NOT_APPLICABLE` sono risultati validi.
6. Il modello non vede outcome Alembic né modifica file, DB, issue o configurazioni.
7. Il giudizio finale conserva limiti di trasferibilità: mercato, periodo, source, event type,
   holding horizon, long/short e costi.
8. Il registry H01–H22 completo viene incluso in ogni prompt di estrazione e review.
9. Le linee probatorie vengono conservate integralmente; non sono troncate a una lunghezza fissa.
10. Un lock advisory impedisce due orchestratori concorrenti sul singolo slot del nodo 1.

## Artefatti

- `HYPOTHESES.md`: matrice congelata delle ipotesi;
- `SOURCE_MANIFEST.tsv`: fonti iniziali e categoria;
- `NODE_CONTRACT.md`: contratto dei job e stop rule;
- `node-output/`: output JSONL append-only generato dai due nodi;
- report finale: `../2026-08-28-s4-deep-web-validation.md`, prodotto dopo verifica.

## Runner persistente

Il protocollo v4 gira come unità transiente utente
`alembic-s4-literature-v4.service`, con `Restart=on-failure` e ledger append-only. L'unità termina
quando il manifest è completo; non modifica S4, database o issue.

Controlli read-only:

```bash
systemctl --user show alembic-s4-literature-v4.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStatus
journalctl --user -u alembic-s4-literature-v4.service -n 50 --no-pager
tail -n 20 node-output/run_ledger.jsonl
```

Una fonte `SOURCE_UNAVAILABLE` o `SOURCE_INCOMPLETE` si riapre senza cancellare il ledger tramite
una campagna nominata e una lista esplicita. Il budget di due tentativi è indipendente per campagna
e persiste fra i suoi restart:

```bash
.venv/bin/python scripts/s4_cluster_literature.py \
  --manifest docs/research/s4-web-validation-2026-08-28/SOURCE_MANIFEST.tsv \
  --output-dir docs/research/s4-web-validation-2026-08-28/node-output \
  --retry-campaign recovery-2026-09-01 \
  --source ACA002 --source ACA007 --source MET001 --source IND007
```

La campagna non riapre fonti già completate e non può essere usata senza almeno un `--source`.
Le copie equivalenti recuperate da repository istituzionali vivono nel manifest separato
`SOURCE_RECOVERY_MANIFEST.tsv`; identità, provenienza, accesso e casi non trovati sono documentati
in `SOURCE_RECOVERY_2026-09-01.md`. Il manifest originale resta congelato e invariato.
