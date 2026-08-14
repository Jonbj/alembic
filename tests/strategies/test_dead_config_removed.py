"""Regression test for issue #177 — dead `from_yaml` config surface removed.

S1Config / S3Config un tempo esponevano un `from_yaml` classmethod che leggeva
un file `config/s*_strategy.yaml`. Il metodo non aveva *alcun* call site nel path
runtime (le strategie sono istanziate con il costruttore nudo), per cui il file
yaml era una falsa superficie di taratura: un operatore che lo editava credeva di
aver tarato la strategia senza alcun effetto. Vedi issue #177 e
`docs/audits/strategies/S1/07_bugs.md` (BUG-1).

Questo test assicura che:
  1. la falsa superficie (`from_yaml` + file yaml orfano) resti rimossa;
  2. i default della dataclass — l'unica configurazione reale — non cambino
     (nessun cambiamento di comportamento runtime).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest.engine.types import RebalanceFrequency
from src.strategies.s1.strategy import S1Config
from src.strategies.s3.strategy import S3Config

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestDeadFromYamlRemoved:
    """La falsa superficie di taratura via yaml non deve riapparire."""

    @pytest.mark.parametrize("config_cls", [S1Config, S3Config])
    def test_no_from_yaml_method(self, config_cls: type) -> None:
        # Il classmethod morto è stato rimosso: la sua presenza sarebbe la
        # reintroduzione di una superficie di taratura non wired.
        assert not hasattr(config_cls, "from_yaml"), (
            f"{config_cls.__name__}.from_yaml è stato reintdotto: è una "
            "superficie di taratura non wired al path runtime (issue #177)."
        )

    def test_s1_strategy_yaml_removed(self) -> None:
        # Il file yaml orfano non deve esistere: era l'oggetto che sembrava
        # tarabile senza esserlo. (S3 non ha mai avuto un proprio yaml.)
        assert not (REPO_ROOT / "config" / "s1_strategy.yaml").exists(), (
            "config/s1_strategy.yaml è ancora presente: è dead config che "
            "simula una superficie di taratura non wired (issue #177)."
        )


class TestDefaultsAreTheConfig:
    """I default della dataclass *sono* la configurazione reale — non devono
    cambiare (verifica di "nessun cambiamento di comportamento runtime")."""

    def test_s1_defaults_unchanged(self) -> None:
        cfg = S1Config()
        assert cfg.strategy_id == "S1"
        assert cfg.lookbacks == (21, 63, 126, 252)
        assert cfg.vol_window_signal == 63
        assert cfg.vol_window_sizing == 60
        assert cfg.target_vol == 0.10
        assert cfg.max_weight == 0.20
        assert cfg.signal_threshold == 0.0
        assert cfg.rebalance_frequency is RebalanceFrequency.MONTHLY

    def test_s3_defaults_unchanged(self) -> None:
        cfg = S3Config()
        assert cfg.strategy_id == "S3"
        assert cfg.lookback == 252
        assert cfg.beta_window == 252
        assert cfg.n_deciles == 10
        assert cfg.target_vol == 0.10
        assert cfg.max_weight == 0.20
        assert cfg.long_decile == 10
        assert cfg.short_decile == 1
        assert cfg.rebalance_frequency is RebalanceFrequency.MONTHLY