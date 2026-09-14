"""Seam 3 — isolamento della PoC Twelve Data (#458) dal path live.

La PoC deve poter girare senza MAI toccare il path che alimenta segnali/ordini:
- nessuna import da moduli live (`src.store.redis_store`, `src.workers.sentiment`,
  `src.connectors.alpaca_news`, `src.brokers.*`, `celery`);
- nessuna scrittura su `news_log`, `news:queue`, o qualunque Redis key del
  tipo `signal:*` / `news:dedup:*` / `news:queue:*` (escludendo le docstring,
  che documentano esattamente cosa NON va toccato).

Protezione statica (AST): un futuro refactor che ricolleghi accidentalmente la
PoC al path live fa fallire questo test prima di entrare in produzione.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# I due file sotto esame: il connettore (biblioteca) e lo script PoC.
TARGETS = [
    REPO_ROOT / "src" / "connectors" / "twelve_data_press_releases.py",
    REPO_ROOT / "scripts" / "poc_twelve_data_shadow.py",
]

# Moduli del path live che NON devono mai essere importati da questi file.
FORBIDDEN_IMPORTS = {
    # storage/Redis live
    "src.store.redis_store",
    "src.store.redis_keys",
    # sentiment worker e downstream che consumano il path live
    "src.workers.sentiment",
    "src.workers.sentiment_worker",
    # connettori news del path live (la PoC non li deve chiamare/aggregare)
    "src.connectors.alpaca_news",
    "src.connectors.finnhub_news",
    "src.connectors.marketaux",
    "src.connectors.gdelt",
    "src.connectors.rss",
    "src.connectors.sec_edgar",
    # broker
    "src.brokers.alpaca_adapter",
    "src.brokers.ibkr_adapter",
    # celery (la PoC e' FUORI dal beat di produzione — vincolo nel corpo issue)
    "celery",
    "src.workers.celery_app",
}

# Stringhe vietate (escluse le docstring): scritture dirette a tabelle/chiavi
# del path live. I test che confrontano tabelle/key usano il modulo `ast` e
# estraggono solo Constant dentro `Call` (es. cur.execute(STRING)), ignorando
# le docstring che documentano la regola.
FORBIDDEN_LIVE_NAMES = {
    "news_log",                  # tabella live delle news
    "news:queue",                # Redis queue live
    "news:queue:item",           # tipo di messaggio nella coda live
    "news:dedup",                # dedup state live
    "signal:current",            # stato segnale live
    "signal:history",            # storico segnali live
}


def _module_docstring_ranges(tree: ast.Module) -> set[int]:
    """Ritorna i range di righe coperte dalle docstring di modulo/classe/funzione.

    Le docstring documentano cosa NON va toccato: vanno escluse dal check sulle
    stringhe letterali per non generare falsi positivi.
    """
    ranges: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    start = body[0].value.lineno
                    end = getattr(body[0].value, "end_lineno", start)
                    ranges.update(range(start, end + 1))
    return ranges


def _import_stmts(tree: ast.AST) -> list[ast.stmt]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]


def _call_string_args(tree: ast.AST, func_name: str) -> list[tuple[int, str]]:
    """Ritorna le stringhe passate come argomento a `func_name(...)`.

    Utile per catturare query SQL (`cur.execute(...)`) senza confondersi con
    import/docstring.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != func_name:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append((arg.lineno, arg.value))
    return out


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_no_live_path_imports(path: Path):
    """Nessuna import da moduli del path live: protezione AST statica."""
    assert path.exists(), f"File PoC mancante: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    leaked = []
    for stmt in _import_stmts(tree):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                full = alias.name
                if full in FORBIDDEN_IMPORTS or any(
                    full == bad or full.startswith(bad + ".")
                    for bad in FORBIDDEN_IMPORTS
                ):
                    leaked.append(full)
        elif isinstance(stmt, ast.ImportFrom):
            module = stmt.module or ""
            if module in FORBIDDEN_IMPORTS or any(
                module == bad or module.startswith(bad + ".")
                for bad in FORBIDDEN_IMPORTS
            ):
                leaked.append(f"{module} (from ... import ...)")
    assert not leaked, (
        f"{path.relative_to(REPO_ROOT).as_posix()} importa moduli del path live: "
        f"{leaked}. La PoC deve restare shadow."
    )


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_no_live_store_references_in_sql(path: Path):
    """Le query SQL (stringhe dentro `cur.execute(...)`) non nominano store live.

    Le docstring di modulo/classe/funzione sono escluse perche' documentano
    esattamente cosa NON va toccato.
    """
    assert path.exists(), f"File PoC mancante: {path}"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    docstring_lines = _module_docstring_ranges(tree)

    leaked: list[tuple[str, int]] = []
    for lineno, sql in _call_string_args(tree, "execute"):
        if lineno in docstring_lines:
            continue
        for bad in FORBIDDEN_LIVE_NAMES:
            if bad in sql:
                leaked.append((bad, lineno))

    assert not leaked, (
        f"{path.relative_to(REPO_ROOT).as_posix()} contiene riferimenti a store live "
        f"in query SQL: {leaked}. La PoC deve restare shadow."
    )


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_poc_only_touches_poc_tables(path: Path):
    """Le tabelle menzionate nelle query SQL sono solo quelle della PoC.

    Estratte come token dopo `FROM|INTO|UPDATE|TABLE IF NOT EXISTS` dentro le
    stringhe passate a `cur.execute(...)`. Le docstring sono escluse.
    """
    import re

    assert path.exists(), f"File PoC mancante: {path}"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    docstring_lines = _module_docstring_ranges(tree)

    # Token dopo FROM/INTO/UPDATE/TABLE IF NOT EXISTS: deve iniziare con una
    # lettera o underscore ed essere seguito da spazio, `;`, `(`, `,` o fine
    # stringa. Esclude `SET`, `VALUES`, ecc. che seguono UPDATE.
    table_pat = re.compile(
        r"(?:FROM|INTO|UPDATE|TABLE\s+IF\s+NOT\s+EXISTS)\s+"
        r"([a-z_][a-z0-9_:]*)"
        r"(?=[\s;,()]|$)",
        re.IGNORECASE,
    )

    found: set[str] = set()
    for lineno, sql in _call_string_args(tree, "execute"):
        if lineno in docstring_lines:
            continue
        for m in table_pat.finditer(sql):
            name = m.group(1).lower()
            # Esclude keyword SQL comuni che seguono UPDATE ma non sono tabelle.
            if name in {"set", "values", "where"}:
                continue
            found.add(name)

    allowed = {"news_poc_samples", "news_poc_request_budget"}
    leaked = found - allowed
    assert not leaked, (
        f"{path.relative_to(REPO_ROOT).as_posix()} tocca tabelle fuori dalla PoC: "
        f"{sorted(leaked)}. Consentite: {sorted(allowed)}."
    )