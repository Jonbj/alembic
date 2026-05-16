#!/usr/bin/env python3
"""Ensemble LLM Query Runner — esegue un prompt su più modelli e aggrega le risposte.

Usage:
    # Ollama locale (default)
    python scripts/ensemble.py --prompt "Classifica le top 3 news API" --models-file models.md

    # OpenRouter (cloud, richiede OPENROUTER_API_KEY)
    export OPENROUTER_API_KEY=sk-...
    python scripts/ensemble.py --prompt "..." --backend openrouter

    # Salva output e aggrega
    python scripts/ensemble.py --prompt "..." --output /tmp/ensemble_out.json --summarize

L'idea: diversi modelli vedono lo stesso problema da angolazioni diverse.
L'aggregazione finale (opzionale) estrae il meglio di ogni risposta.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_models_md(path: str) -> list[str]:
    """Estrae gli ID modello dal file models.md.

    Si aspetta un file markdown con tabelle. I modelli sono nella
    prima colonna, backtick-quoted, es.:
        | `model-id:cloud` | Tipo | Note |
    """
    text = Path(path).read_text()
    models = []
    for line in text.splitlines():
        # Match solo righe di tabella markdown: | `model-id` | ...
        m = re.match(r"^\|\s*`([^`]+)`\s*\|", line.strip())
        if m:
            model_id = m.group(1).strip()
            if model_id and not model_id.startswith("http") and not model_id.startswith("/"):
                models.append(model_id)
    # Deduplica mantenendo ordine
    seen = set()
    out = []
    for m in models:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


async def _query_ollama(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    host: str = "http://localhost:11434",
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Chiama Ollama /api/generate."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7},
    }
    try:
        resp = await client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return {
            "model": model,
            "backend": "ollama",
            "response": data.get("response", "").strip(),
            "done": data.get("done", False),
            "duration_ms": data.get("total_duration", 0) // 1_000_000,
            "error": None,
            "timestamp": _now(),
        }
    except Exception as e:
        return {
            "model": model,
            "backend": "ollama",
            "response": None,
            "error": str(e),
            "timestamp": _now(),
        }


async def _query_openrouter(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    api_key: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Chiama OpenRouter /v1/chat/completions.

    OpenRouter supporta decine di modelli cloud (Claude, GPT, Qwen, DeepSeek,
    Mistral, Gemini, ecc.) tramite un unico endpoint e una sola API key.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ensemble-runner",
        "X-Title": "Ensemble Runner",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})
        return {
            "model": model,
            "backend": "openrouter",
            "response": msg.get("content", "").strip(),
            "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "error": None,
            "timestamp": _now(),
        }
    except Exception as e:
        return {
            "model": model,
            "backend": "openrouter",
            "response": None,
            "error": str(e),
            "timestamp": _now(),
        }


async def run_ensemble(
    prompt: str,
    models: list[str],
    backend: str,
    host: str | None = None,
    api_key: str | None = None,
    max_concurrent: int = 5,
    timeout: float = 120.0,
) -> list[dict[str, Any]]:
    """Esegue il prompt su tutti i modelli in parallelo con limitazione concorrenza."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_one(model: str) -> dict[str, Any]:
        async with semaphore:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                if backend == "ollama":
                    return await _query_ollama(
                        client, model, prompt, host or "http://localhost:11434", timeout
                    )
                elif backend == "openrouter":
                    if not api_key:
                        return {
                            "model": model,
                            "backend": "openrouter",
                            "response": None,
                            "error": "OPENROUTER_API_KEY mancante",
                            "timestamp": _now(),
                        }
                    return await _query_openrouter(client, model, prompt, api_key, timeout)
                else:
                    return {
                        "model": model,
                        "backend": backend,
                        "response": None,
                        "error": f"Backend sconosciuto: {backend}",
                        "timestamp": _now(),
                    }

    return await asyncio.gather(*(_run_one(m) for m in models))


def _format_results(results: list[dict[str, Any]]) -> str:
    """Formatta i risultati in markdown leggibile."""
    lines = ["# Ensemble Results\n"]
    for r in results:
        model = r["model"]
        backend = r["backend"]
        ts = r["timestamp"]
        lines.append(f"## {model} ({backend})  —  {ts}\n")
        if r.get("error"):
            lines.append(f"**ERROR:** {r['error']}\n")
        else:
            resp = r.get("response", "")
            lines.append(f"```\n{resp}\n```\n")
        lines.append("---\n")
    return "\n".join(lines)


async def summarize_ensemble(
    results: list[dict[str, Any]],
    backend: str,
    model: str = "claude-sonnet-4-7",
    host: str | None = None,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Usa un singolo modello 'aggregator' per estrarre il meglio da tutte le risposte.

    Il prompt di aggregazione chiede di:
      1. Identificare punti di accordo tra i modelli.
      2. Evidenziare insight unici di ciascun modello.
      3. Produrre una risposta sintetica finale.
    """
    valid = [r for r in results if r.get("response") and not r.get("error")]
    if not valid:
        return {"model": model, "response": "Nessuna risposta valida da aggregare.", "error": None}

    parts = []
    for i, r in enumerate(valid, 1):
        parts.append(f"=== RISPOSTA {i} — Modello: {r['model']} ===\n{r['response']}\n")

    agg_prompt = (
        "Sei un analista senior. Hai ricevuto le risposte di diversi modelli LLM "
        "allo stesso prompt. Il tuo compito è sintetizzare il meglio di ogni risposta "
        "in un unico output finale.\n\n"
        "Istruzioni:\n"
        "1. Identifica i punti su cui tutti i modelli concordano.\n"
        "2. Estrai insight unici o particolari che solo un modello ha proposto.\n"
        "3. Se ci sono contraddizioni, segnalale e spiega quale interpretazione è più solida.\n"
        "4. Produrre una risposta finale strutturata, concisa e di alta qualità.\n\n"
        f"Prompt originale: {valid[0].get('_original_prompt', '(non disponibile)')}\n\n"
        "Risposte dei modelli:\n\n" + "\n".join(parts)
    )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        if backend == "ollama":
            return await _query_ollama(client, model, agg_prompt, host or "http://localhost:11434", timeout)
        else:
            if not api_key:
                return {"model": model, "response": None, "error": "OPENROUTER_API_KEY mancante per summarize"}
            return await _query_openrouter(client, model, agg_prompt, api_key, timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensemble LLM Query Runner")
    parser.add_argument("--prompt", "-p", required=True, help="Prompt da inviare a tutti i modelli")
    parser.add_argument("--models", nargs="+", help="Lista esplicita di modelli (sovrascrive --models-file)")
    parser.add_argument("--models-file", "-m", default="models.md", help="File markdown con lista modelli")
    parser.add_argument("--backend", choices=["ollama", "openrouter"], default="ollama", help="Backend API")
    parser.add_argument("--host", default="http://localhost:11434", help="Host Ollama (solo backend=ollama)")
    parser.add_argument("--api-key", default=os.environ.get("OPENROUTER_API_KEY", ""), help="API key OpenRouter")
    parser.add_argument("--max-models", type=int, default=0, help="Max modelli da usare (0 = tutti)")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Chiamate parallele massime")
    parser.add_argument("--timeout", type=float, default=120.0, help="Timeout per chiamata (secondi)")
    parser.add_argument("--output", "-o", help="File JSON di output")
    parser.add_argument("--markdown", help="File markdown di output")
    parser.add_argument("--summarize", action="store_true", help="Aggrega le risposte con un modello riassuntore")
    parser.add_argument("--aggregator-model", default="claude-sonnet-4-7", help="Modello per il riassunto finale")
    args = parser.parse_args()

    if not Path(args.models_file).exists():
        print(f"ERRORE: File modelli non trovato: {args.models_file}", file=sys.stderr)
        return 1

    if args.models:
        models = args.models
    else:
        models = parse_models_md(args.models_file)
        if not models:
            print(f"ERRORE: Nessun modello trovato in {args.models_file}", file=sys.stderr)
            return 1
        if args.max_models > 0:
            models = models[: args.max_models]

    print(f"[ensemble] Modelli selezionati: {len(models)}")
    for m in models:
        print(f"  → {m}")
    print(f"[ensemble] Backend: {args.backend}")
    print(f"[ensemble] Prompt: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print("-" * 60)

    results = asyncio.run(
        run_ensemble(
            prompt=args.prompt,
            models=models,
            backend=args.backend,
            host=args.host,
            api_key=args.api_key,
            max_concurrent=args.max_concurrent,
            timeout=args.timeout,
        )
    )

    # Annota il prompt originale per il riassunto
    for r in results:
        r["_original_prompt"] = args.prompt

    ok = sum(1 for r in results if not r.get("error"))
    ko = len(results) - ok
    print(f"[ensemble] Completato: {ok} OK, {ko} ERRORI")

    # Riassunto finale (opzionale)
    summary = None
    if args.summarize:
        print(f"[ensemble] Aggregazione con modello: {args.aggregator_model}")
        summary = asyncio.run(
            summarize_ensemble(
                results,
                backend=args.backend,
                model=args.aggregator_model,
                host=args.host,
                api_key=args.api_key,
                timeout=args.timeout,
            )
        )
        print(f"[ensemble] Riassunto: {len(summary.get('response') or '')} chars")

    # Output JSON
    payload = {
        "meta": {
            "prompt": args.prompt,
            "backend": args.backend,
            "models_used": models,
            "timestamp": _now(),
            "ok": ok,
            "errors": ko,
        },
        "results": results,
    }
    if summary:
        payload["summary"] = summary

    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(json_text)
        print(f"[ensemble] JSON salvato: {args.output}")
    else:
        print(json_text)

    # Output markdown
    if args.markdown:
        md = _format_results(results)
        if summary and summary.get("response"):
            md += f"\n# Summary ({summary['model']})\n\n{summary['response']}\n"
        Path(args.markdown).write_text(md)
        print(f"[ensemble] Markdown salvato: {args.markdown}")

    return 0 if ko == 0 else 0  # exit 0 anche con errori parziali


if __name__ == "__main__":
    sys.exit(main())
