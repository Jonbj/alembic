"""Guardia: le rotte di lettura /api/strategies restano rimosse (2026-09-02).

Questo modulo verificava le rotte di lettura hardcoded (`GET /api/strategies`,
`/{id}`, `/{id}/backtest`, `/{id}/gates`, `/{id}/sensitivity`). Sono state
eliminate insieme alla pagina Strategies del frontend perche' servivano snapshot
congelati al 2026-05-30 (S1) e al 2026-06-15 (S4) presentandoli come stato corrente:
`total_trades` 1247 contro 103 righe reali, l'universo del *backtest* (15 ETF) al posto
delle azioni realmente scambiate, un heatmap di sensitivity generato da una formula
gaussiana, e un pannello di gate con soglie inventate piu' severe di quelle vere.

I test qui sotto non riproducono quel comportamento: bloccano il ritorno. Se qualcuno
rimette una rotta di lettura su questo router, questi test la vedono e la rifiutano,
perche' il difetto non era l'implementazione ma l'idea di servire metriche da un
dizionario Python.

Lo stato di autorizzazione — l'unica parte corretta di quella superficie — vive ora su
`GET /portfolio/status`, alimentato da `strategy_lifecycle` e `config/strategies.yaml`,
ed e' coperto da `test_portfolio_status_authorization_fields`.

Le tre POST del promotion gate restano e sono coperte da
`tests/test_p2_promotion_wiring.py`.
"""

from fastapi.testclient import TestClient

from src.api.main import app

# Rotte di lettura eliminate. Un 404 qui e' il comportamento voluto.
_REMOVED_READ_ROUTES = [
    "/api/strategies",
    "/api/strategies/s1",
    "/api/strategies/s1/backtest",
    "/api/strategies/s1/gates",
    "/api/strategies/s1/sensitivity",
    "/api/strategies/s3",
    "/api/strategies/s4/gates",
]


def test_removed_read_routes_are_gone():
    """Nessuna rotta GET su /api/strategies deve rispondere 200."""
    tc = TestClient(app)
    still_alive = [p for p in _REMOVED_READ_ROUTES if tc.get(p).status_code == 200]
    assert still_alive == [], (
        f"Rotte di lettura risorte su /api/strategies: {still_alive}. "
        "Servivano snapshot hardcoded; se servono metriche di strategia vanno lette "
        "dal DB, non da un dizionario nel modulo delle route."
    )


def test_no_get_routes_registered_on_the_strategies_router():
    """Il router /api/strategies espone solo POST (promote/approve/demote)."""
    offenders = [
        (r.path, sorted(r.methods - {"HEAD", "OPTIONS"}))
        for r in app.routes
        if getattr(r, "path", "").startswith("/api/strategies")
        and "GET" in getattr(r, "methods", set())
    ]
    assert offenders == [], f"GET registrati su /api/strategies: {offenders}"


def test_promotion_endpoints_survived_the_removal():
    """Le tre POST di governance non devono essere state rimosse per sbaglio."""
    paths = {
        (r.path, m)
        for r in app.routes
        for m in getattr(r, "methods", set())
        if getattr(r, "path", "").startswith("/api/strategies")
    }
    for suffix in ("promote", "approve", "demote"):
        assert ("/api/strategies/{strategy_id}/" + suffix, "POST") in paths, (
            f"POST /api/strategies/{{strategy_id}}/{suffix} e' sparito: la rimozione "
            "delle rotte di lettura non deve toccare il promotion gate."
        )


def test_module_keeps_no_hardcoded_strategy_metrics():
    """Nessun dizionario di metriche congelate residuo nel codice del modulo.

    Il docstring del modulo cita apposta quei nomi per spiegare cosa e' stato tolto,
    quindi va escluso prima di cercarli: il controllo e' sul codice, non sulla prosa.
    """
    import ast
    from pathlib import Path

    src = Path("src/api/routes/strategies.py").read_text()
    tree = ast.parse(src)
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    code = "\n".join(ast.unparse(node) for node in body)

    for banned in ("oos_sharpe", "SENSITIVITY_", "GATES_", "total_trades",
                   "S1_DETAIL", "S4_DETAIL", "_load_equity_curve", "sensitivity"):
        assert banned not in code, (
            f"'{banned}' e' tornato nel codice di src/api/routes/strategies.py. "
            "Le metriche di strategia non tornano in un dizionario Python."
        )
