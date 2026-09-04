#!/usr/bin/env python3
"""Train and compare an offline FinBERT distillation checkpoint (#466).

The command only reads PostgreSQL and writes local files below ``--output-dir``.
It is intentionally disconnected from FinBERTClient and the live sentiment path.

Example (from a host with the production Postgres port exposed):

    .venv/bin/python scripts/train_finbert_distillation.py \
      --database-url postgresql://trading:trading@localhost:5432/trading
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.llm.finbert_distillation import (  # noqa: E402
    DISTILLATION_QUERY,
    MAX_TOKENS,
    MODEL_NAME,
    chronological_split,
    compute_metrics,
    example_manifest,
    fetch_distillation_examples,
    predict_polarities,
    save_checkpoint,
    train_model,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/finbert_distillation"))
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--validation-fraction", type=float, default=0.20)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    parser.add_argument("--seed", type=int, default=466)
    parser.add_argument(
        "--max-examples",
        type=int,
        help="Use only the oldest N rows (smoke tests only; omitted for the real report).",
    )
    parser.add_argument(
        "--dataset-only",
        action="store_true",
        help="Validate and export the temporal dataset without loading FinBERT.",
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto"
    )
    return parser


def _device(choice: str) -> torch.device:
    if choice == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda requested but CUDA is unavailable")
    if choice == "auto":
        choice = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(choice)


def _checkpoint_digest(checkpoint: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in checkpoint.rglob("*") if item.is_file()):
        digest.update(path.relative_to(checkpoint).as_posix().encode())
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _recommendation(base: dict, tuned: dict) -> str:
    improves_price_metrics = tuned["ic"] > base["ic"] and tuned["hit_rate"] >= base["hit_rate"]
    improves_imitation = tuned["mae"] < base["mae"]
    if improves_price_metrics and improves_imitation:
        return (
            "CANDIDATO, NON FLIP DURANTE IL FREEZE: il tuned domina il base sullo "
            "stesso holdout; rivalutare l'attivazione dopo il 2026-09-28."
        )
    return (
        "NO FLIP: il tuned non domina il base su IC, hit-rate e MAE nello stesso "
        "holdout temporale."
    )


def _render_report(summary: dict) -> str:
    base = summary["metrics"]["base"]
    tuned = summary["metrics"]["tuned"]

    def number(value: float) -> str:
        return "n/a" if not torch.isfinite(torch.tensor(value)) else f"{value:.4f}"

    return "\n".join(
        [
            "# FinBERT distillation — confronto offline",
            "",
            f"Generato: {summary['generated_at']}",
            "",
            "Il checkpoint e' stato addestrato esclusivamente su verdict ensemble cloud "
            "non-fallback con forward return 1d disponibile. Lo split e' cronologico e "
            "l'holdout e' successivo a tutte le righe di training.",
            "",
            "| split | n | inizio | fine |",
            "|---|---:|---|---|",
            (
                f"| train | {summary['dataset']['train_n']} | "
                f"{summary['dataset']['train_start']} | {summary['dataset']['train_end']} |"
            ),
            (
                f"| validation | {summary['dataset']['validation_n']} | "
                f"{summary['dataset']['validation_start']} | "
                f"{summary['dataset']['validation_end']} |"
            ),
            "",
            "| modello | n | IC Spearman vs return 1d | hit-rate | MAE vs teacher |",
            "|---|---:|---:|---:|---:|",
            (
                f"| FinBERT base | {base['n']} | {number(base['ic'])} | "
                f"{number(base['hit_rate'])} | {number(base['mae'])} |"
            ),
            (
                f"| FinBERT tuned | {tuned['n']} | {number(tuned['ic'])} | "
                f"{number(tuned['hit_rate'])} | {number(tuned['mae'])} |"
            ),
            "",
            f"Loss media per epoca: {summary['training']['epoch_losses']}",
            "",
            f"Raccomandazione: **{summary['recommendation']}**",
            "",
            "Il checkpoint non e' letto da alcun componente live. La sua eventuale "
            "promozione richiede una decisione dell'operatore dopo il freeze.",
            "",
        ]
    )


def _range(examples) -> tuple[str, str]:
    return examples[0].generated_at.isoformat(), examples[-1].generated_at.isoformat()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_examples is not None and args.max_examples < 2:
        raise SystemExit("--max-examples must be at least 2")

    with psycopg2.connect(args.database_url) as connection:
        connection.set_session(readonly=True)
        examples = fetch_distillation_examples(connection)
    if args.max_examples is not None:
        examples = examples[: args.max_examples]
    train, validation = chronological_split(examples, args.validation_fraction)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(example_manifest(examples), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    train_start, train_end = _range(train)
    validation_start, validation_end = _range(validation)
    dataset_summary = {
        "total_n": len(examples),
        "train_n": len(train),
        "validation_n": len(validation),
        "train_start": train_start,
        "train_end": train_end,
        "validation_start": validation_start,
        "validation_end": validation_end,
        "manifest": str(manifest_path),
    }
    print(json.dumps(dataset_summary, indent=2))
    if args.dataset_only:
        return 0

    device = _device(args.device)
    print(f"Loading {args.model_name} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name)
    base_predictions = predict_polarities(
        model,
        tokenizer,
        validation,
        device=device,
        batch_size=args.batch_size,
        max_tokens=args.max_tokens,
    )
    base_metrics = compute_metrics(base_predictions, validation)

    print(f"Training on {len(train)} examples for {args.epochs} epoch(s)...")
    epoch_losses = train_model(
        model,
        tokenizer,
        train,
        device=device,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_tokens=args.max_tokens,
        seed=args.seed,
    )
    tuned_predictions = predict_polarities(
        model,
        tokenizer,
        validation,
        device=device,
        batch_size=args.batch_size,
        max_tokens=args.max_tokens,
    )
    tuned_metrics = compute_metrics(tuned_predictions, validation)

    generated_at = datetime.now(timezone.utc).isoformat()
    checkpoint = args.output_dir / "checkpoint"
    metadata = {
        "generated_at": generated_at,
        "base_model": args.model_name,
        "dataset": dataset_summary,
        "query": DISTILLATION_QUERY.strip(),
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "max_tokens": args.max_tokens,
            "seed": args.seed,
            "device": str(device),
            "loss": "MSE(soft polarity) + cross_entropy(sign)",
            "epoch_losses": epoch_losses,
        },
        "metrics": {"base": base_metrics, "tuned": tuned_metrics},
    }
    save_checkpoint(model, tokenizer, checkpoint, metadata)
    metadata["checkpoint"] = {
        "path": str(checkpoint),
        "sha256": _checkpoint_digest(checkpoint),
    }
    metadata["recommendation"] = _recommendation(base_metrics, tuned_metrics)
    (args.output_dir / "result.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(
        _render_report(metadata), encoding="utf-8"
    )
    print(_render_report(metadata))
    print(f"Checkpoint: {checkpoint} ({metadata['checkpoint']['sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
