"""Il report alpha-miss deve rendere il blocco osservazionale #409."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"


def test_prompt_richiede_marker_calendario_e_copertura_raw_per_settore():
    prompt = SCRIPT.read_text()

    assert "no_news_backstop.per_symbol" in prompt
    assert "observed_catalysts" in prompt
    assert "no_news_backstop.per_sector" in prompt
    assert "raw_news_coverage_rate" in prompt


def test_prompt_vieta_di_leggere_il_volume_eod_come_segnale_ex_ante():
    prompt = SCRIPT.read_text()

    assert "POST_HOC_EOD" in prompt
    assert "non e' un segnale point-in-time" in prompt
