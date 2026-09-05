"""Regressioni per il deploy del flusso news Alpaca WebSocket (#455)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_avvia_il_news_stream_come_servizio_dedicato():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    service = compose["services"]["worker-news-stream"]

    assert "--service worker-news-stream --" in service["command"]
    assert "python -m src.workers.news_stream" in service["command"]
    assert service["restart"] == "unless-stopped"
    assert service["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert service["depends_on"]["redis"]["condition"] == "service_healthy"


def test_riconciliazione_include_il_news_stream_fra_i_backend():
    deploy_script = (ROOT / "scripts" / "deploy_reconcile.sh").read_text()

    backend_line = next(
        line for line in deploy_script.splitlines()
        if line.startswith("SERVIZI_BACKEND=")
    )

    assert "worker-news-stream" in backend_line
