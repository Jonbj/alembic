-- Migration 076: promotion_blocked in strategy_lifecycle (#470).
--
-- _fetch_lifecycle_row (src/strategies/promotion.py) seleziona questa colonna
-- da sempre, ma la migrazione 025 non l'ha mai creata: sul DB live promote e
-- approve rispondevano 500 (UndefinedColumn), e demote — che passa dalla stessa
-- SELECT — era rotta allo stesso modo. Fail-closed per rottura, non per stato:
-- il gate non ha mai girato contro il DB reale.
--
-- La verita' del flag vive nella tabella, come per `mode`: la 025 dichiara
-- strategy_lifecycle fonte canonica e config/strategies.yaml seme di bootstrap.
-- Lo YAML resta il seme mostrato da /portfolio/status; l'errore del gate
-- prescrive di sbloccare in entrambi i posti.
--
-- Backfill: DEFAULT TRUE porta ogni riga esistente a bloccata. Copre i due
-- blocchi dichiarati nello YAML (S1, S4) e lascia bloccate anche S2 e S7,
-- che nello YAML non compaiono o non dichiarano il flag: oggi tutte le
-- promozioni sono bloccate di fatto (errore 500), e un fix di correttezza non
-- deve aprire nessun gate. Sbloccare una strategia resta una decisione
-- dell'operatore, fuori dal freeze #171.
--
-- Freeze #171, evidenza al 2026-09-15 (review PR #598): la migrazione non
-- cambia nessun esito raggiungibile del gate. Sul DB live promoted_at e' NULL
-- su tutte le righe e strategy_lifecycle_audit non contiene azioni
-- 'requested'/'approved' (solo il blocco manuale di S7 del 2026-07-03): il
-- gate non ha mai concesso una promozione, perche' ogni chiamata moriva
-- dentro la SELECT. Dopo la 076 ogni chiamata e' rifiutata dal check #5
-- (422 invece di 500): stessa decisione, causa visibile. La colonna e' letta
-- solo da _fetch_lifecycle_row — nessun percorso di trading, nessuna serie
-- osservata. La variante «backfill dallo YAML» aprirebbe S2 e S7: sarebbe
-- quella, non questa, la modifica di comportamento in freeze.

ALTER TABLE strategy_lifecycle
    ADD COLUMN IF NOT EXISTS promotion_blocked BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN strategy_lifecycle.promotion_blocked IS
    'Gate flag: TRUE blocca ogni promozione (#470). Fonte canonica del flag; lo YAML e'' il seme. Default TRUE = fail-closed: riga nuova nasce bloccata.';
