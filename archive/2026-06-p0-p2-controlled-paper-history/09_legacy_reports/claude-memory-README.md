# Claude Memory — Cross-Machine Handoff

Questi file sono l'export della memoria persistente di Claude per questo progetto.

## Come usarli su un'altra macchina

1. Clona / fai pull del repo
2. Copia i file nella directory memoria di Claude:

```bash
MEMORY_DIR=~/.claude/projects/$(pwd | sed 's|/|-|g' | sed 's|^-||')/memory
mkdir -p "$MEMORY_DIR"
cp docs/claude-memory/*.md "$MEMORY_DIR/"
```

3. Avvia una nuova sessione Claude Code nella directory del progetto:
```bash
cd /path/to/trading
claude
```

Claude leggerà automaticamente `MEMORY.md` e avrà il contesto completo del progetto.

## Ultimo aggiornamento

2026-05-08 — export manuale prima di cambio macchina.
