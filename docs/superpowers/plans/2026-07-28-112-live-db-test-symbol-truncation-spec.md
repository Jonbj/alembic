# Spec — #112: test live-DB fallisce con `StringDataRightTruncation`

Part of #21 · Issue: #112 · Branch: `fix/112-live-db-test-symbol-truncation`

## Contesto

`tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` fallisce su
main pulito con `psycopg2.errors.StringDataRightTruncation: value too long for type character
varying(20)`. È l'**unico** test rosso della suite (3170 passed, 1 skipped, questo fallisce).

## Diagnosi (già fatta — non ripartire da zero)

Il test usa:

```python
# tests/store/test_pg_store_stop_methods.py:64
symbol = "TEST_STOP_FIXED_AUDIT"   # 21 caratteri
```

`trades.symbol` è `VARCHAR(20)`. 21 > 20 → troncamento rifiutato da Postgres.

**È il dato di test a essere troppo lungo, non la colonna a essere sotto-dimensionata.** Non
esiste un ticker reale di 21 caratteri: allargare la colonna sarebbe la correzione sbagliata e
rimuoverebbe un vincolo che oggi protegge dai simboli spazzatura.

Confronta con gli altri test dello stesso file, che usano nomi corti (`TEST_STOP_3`) e non
falliscono.

## Scope

1. Accorcia il simbolo di test a **≤ 20 caratteri**, mantenendolo riconoscibile come dato di
   test e **univoco** rispetto agli altri simboli del file (serve a non collidere con le righe
   di altri test che cancellano per `symbol`). Es. `TEST_STOP_FIXED_AUD` (19).
2. Verifica che il `finally` del test continui a cancellare la riga con lo stesso simbolo — il
   `DELETE FROM trades WHERE symbol = %s` alla riga ~88 usa la stessa variabile, quindi deve
   restare coerente.
3. Aggiungi una **guardia** che impedisca il ripetersi della classe: un test che asserisce che
   ogni simbolo di test usato in questo file sta entro il limite della colonna. Implementalo
   senza toccare il DB (pura ispezione delle costanti, oppure un helper condiviso
   `_test_symbol(name)` che tronca/valida). Scegli tu la forma; il requisito è che aggiungere
   domani un simbolo da 21 caratteri rompa un test **senza** dover avere un DB.

## Fuori scope

- **Non allargare** `trades.symbol` né alcuna altra colonna. Nessuna migration.
- Non riscrivere il test per non usare il DB: è un test live-DB per scelta, e cambiarne la
  natura è una decisione separata (vedi nota sotto).

## Nota da riportare nella PR (non da risolvere qui)

Questo test scrive su Postgres **di produzione** (`PostgreSQLStore(use_pool=False)` legge la
config reale). È la stessa classe di problema di #119 (test che scrivevano righe reali in
`audit_log`). Qui il `finally` con `DELETE` c'è, quindi non lascia sporcizia, ma la dipendenza
da un DB prod in un test resta. **Segnalalo nella descrizione della PR**; non risolverlo in
questo branch.

## Metodo

TDD: fai girare il test rosso prima (serve un DB raggiungibile; se non ce l'hai, dichiaralo
nella PR e verifica almeno che la guardia nuova sia rossa prima del fix).

## Criteri di accettazione

- `test_fixed_mode_freezes_audit_fields` passa contro il DB live.
- La guardia sulla lunghezza dei simboli è presente e fallisce se si introduce un simbolo
  troppo lungo (dimostralo: rendila rossa temporaneamente e riportalo nella PR).
- Nessuna migration nel diff.
- Suite: 3170+ passed, 0 failed.

## Consegna

Branch `fix/112-live-db-test-symbol-truncation`, un commit, PR con `closes #112`.
**Non mergiare e non deployare**: review e merge li faccio io.
