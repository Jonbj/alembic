"""Motore mensile della manica S3 del POC (#84).

Segnale al close dell'ultima seduta del mese, fill all'open della seduta
successiva (fallback sul close della stessa seduta se l'open non e'
affidabile), fill same-bar vietati, costi letti dal manifest congelato,
delisting come rendimento economico esplicito, walk-forward 60/12/12 con
stato fresco per finestra e invarianza all'ordine.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.manifest import load_manifest
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset
from tests.analysis.s3_poc_util import write_manifest_override

ENGINE = "src.analysis.s3_poc.engine"


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    return load_manifest(write_manifest_override(tmp_path_factory.mktemp("m"), {"universe": {"min_breadth": 3}}))


def pattern_prices(n: int, amplitude: float = 0.004) -> np.ndarray:
    """Pattern deterministico +a/-a: drift nullo, vol positiva."""
    steps = np.where(np.arange(n) % 2 == 0, 1 + amplitude, 1 / (1 + amplitude))
    return 50.0 * np.cumprod(steps)


def hand_dataset(
    n_securities: int = 12,
    start: date = date(2019, 1, 1),
    end: date = date(2020, 12, 31),
    delistings: tuple[tuple[str, date, float, bool], ...] = (),
    amplitude: float = 0.004,
) -> "object":
    """Dataset craftato: serie identiche per tutti i security.

    Segnali identici -> selezione alfabetica (gli ultimi due del decile 10),
    pesi inverse-vol uguali -> cap 10% ciascuno, resto cassa. Prevedibile
    al centesimo per i test di contabilita' del portafoglio.
    """
    from src.analysis.s3_poc.dataset import PitDataset, Provenance

    sessions = pd.bdate_range(start, end)
    n = len(sessions)
    prices = pattern_prices(n, amplitude)
    ids = [f"S{i:02d}" for i in range(n_securities - 2)] + ["ZGONE", "ZMISS"]
    close = pd.DataFrame({sec: prices for sec in ids}, index=sessions)
    open_ = close.copy()
    volume = pd.DataFrame(1e6, index=sessions, columns=ids)
    market_cap = pd.DataFrame(1e10, index=sessions, columns=ids)
    reliable = pd.DataFrame(True, index=sessions, columns=ids)
    rows = []
    dl = pd.DataFrame(columns=["security_id", "delisting_date", "delisting_return", "missing_status"])
    recs = []
    for sec, dl_date, dl_ret, missing in delistings:
        after = sessions > pd.Timestamp(dl_date)
        close.loc[after, sec] = np.nan
        open_.loc[after, sec] = np.nan
        volume.loc[after, sec] = np.nan
        market_cap.loc[after, sec] = np.nan
        reliable.loc[after, sec] = False
        recs.append({
            "security_id": sec, "delisting_date": pd.Timestamp(dl_date),
            "delisting_return": float(dl_ret), "missing_status": bool(missing),
        })
    if recs:
        dl = pd.DataFrame(recs)
    for sec in ids:
        rows.append({
            "security_id": sec, "valid_from": sessions[0], "valid_to": sessions[-1],
            "share_type": "common", "primary_exchange": "NYSE", "sector": "X",
        })
    prov = Provenance(
        vendor="hand", release="1", obtained_at=date(2026, 9, 16),
        files_sha256={}, synthetic=True, qualified=False, qualification_artifact=None,
    )
    market = pd.Series(pattern_prices(n, 0.001), index=sessions)
    return PitDataset(
        provenance=prov, close=close, open=open_, volume=volume,
        market_cap=market_cap, open_reliable=reliable,
        security_master=pd.DataFrame(rows), delistings=dl, market=market,
    )


def drift_dataset(start: date = date(2019, 1, 1), end: date = date(2021, 12, 31)):
    """12 security con drift crescente: il top decile e' deterministicamente
    la coppia con drift piu' alto (indipendente dal rumore, gap ampio)."""
    specs = tuple(
        SecuritySpec(security_id=f"S{i:02d}", daily_vol=0.01, drift=-0.20 + 0.05 * i)
        for i in range(10)
    ) + (
        SecuritySpec(security_id="TOP", daily_vol=0.01, drift=0.35),
        SecuritySpec(security_id="BADTOP", daily_vol=0.01, drift=0.30,
                     open_unreliable_from=start),
    )
    return build_synthetic_dataset(SyntheticSpec(start=start, end=end, securities=specs))


class TestScheduleMensile:
    def test_segnale_a_fine_mese_esecuzione_alla_seduta_dopo(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-06-30"))
        sessions = ds.sessions
        mesi = sessions[(sessions >= pd.Timestamp("2020-01-01")) & (sessions <= pd.Timestamp("2020-06-30"))]
        fine_mese = list(mesi.to_series().groupby([mesi.year, mesi.month]).last())
        # l'ultimo fine-mese (30 giu) non ha seduta successiva dentro la finestra
        assert [r.signal_date for r in res.rebalances] == fine_mese[:5]
        for r in res.rebalances:
            successive = sessions[sessions > r.signal_date]
            assert r.execution_date == successive[0]
            assert r.execution_date > r.signal_date  # mai same-bar

    def test_fill_all_open_della_seduta_successiva(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        for sec, price in r.fill_prices.items():
            if sec == "BADTOP":
                continue  # coperto dal test dedicato al fallback
            assert price == pytest.approx(ds.open.loc[r.execution_date, sec], rel=1e-12)
            assert price != pytest.approx(ds.close.loc[r.signal_date, sec], rel=1e-6)

    def test_open_non_affidabile_riempie_sul_close(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        assert "TOP" in r.fill_prices
        assert "BADTOP" in r.fill_prices
        assert r.fill_prices["TOP"] == pytest.approx(ds.open.loc[r.execution_date, "TOP"], rel=1e-12)
        assert r.fill_prices["BADTOP"] == pytest.approx(ds.close.loc[r.execution_date, "BADTOP"], rel=1e-12)

    def test_open_nan_ma_reliable_riempie_sul_close(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        # TOP ha open NaN sulla seduta di esecuzione ma flag reliable True
        r0 = pd.Timestamp("2020-02-03")  # prima seduta dopo il fine mese di gennaio
        assert r0 in ds.open.index
        ds.open.loc[r0, "TOP"] = np.nan
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        assert r.execution_date == r0
        assert r.fill_prices["TOP"] == pytest.approx(ds.close.loc[r0, "TOP"], rel=1e-12)

    def test_prezzo_mancante_skippa_solo_quel_nome(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        r0 = pd.Timestamp("2020-02-03")
        ds.open.loc[r0, "TOP"] = np.nan
        ds.close.loc[r0, "TOP"] = np.nan
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        assert r.skipped_execution == ("TOP",)
        assert "TOP" not in r.fill_prices
        # il mese dopo TOP rientra (il skip e' locale alla seduta)
        assert "TOP" in res.rebalances[1].fill_prices


class TestCapitaleEDrift:
    def test_nav_in_azioni_con_drift_intra_mese(self, manifest) -> None:
        """Il NAV si muove con i close giornalieri fra un ribilancio e l'altro
        (portafoglio in azioni, non rendimenti pesati statici)."""
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        # primo ribilancio: NAV di esecuzione = capitale iniziale (nulla detenuto)
        nav_exec_gross = manifest.portfolio.initial_capital_usd
        cash = nav_exec_gross * (1.0 - sum(r.weights.values())) - r.cost_usd
        giorni = [d for d in res.nav.index if d > r.execution_date][:4]
        for d in giorni:
            atteso = cash + sum(
                nav_exec_gross * w / r.fill_prices[s] * ds.close.loc[d, s]
                for s, w in r.weights.items()
            )
            assert res.nav.loc[d] == pytest.approx(atteso, rel=1e-9)

    def test_capitale_iniziale_dal_manifest(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        primo = res.nav.index[0]
        assert res.nav.loc[primo] == pytest.approx(manifest.portfolio.initial_capital_usd)


class TestDelisting:
    def test_rendimento_economico_il_giorno_delisting(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = hand_dataset(delistings=(("ZGONE", date(2020, 2, 14), -1.0, False),))
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-07-31"))
        # selezione alfabetica: ZGONE e ZMISS (decile 10 di 12)
        r = res.rebalances[0]
        assert set(r.weights) == {"ZGONE", "ZMISS"}
        assert res.decision_grade is True
        d = pd.Timestamp("2020-02-14")
        nav_exec_gross = manifest.portfolio.initial_capital_usd
        sh = {s: nav_exec_gross * w / r.fill_prices[s] for s, w in r.weights.items()}
        cash = nav_exec_gross * (1.0 - sum(r.weights.values())) - r.cost_usd
        atteso = cash + sh["ZMISS"] * ds.close.loc[d, "ZMISS"] + sh["ZGONE"] * ds.close.loc[d, "ZGONE"] * 0.0
        assert res.nav.loc[d] == pytest.approx(atteso, rel=1e-9)
        # il delisting si vede nel rendimento giornaliero
        assert res.returns.loc[d] < -0.05

    def test_delisting_parziale_rende_il_valore_residuo(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = hand_dataset(delistings=(("ZGONE", date(2020, 2, 14), -0.4, False),))
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-07-31"))
        r = res.rebalances[0]
        d = pd.Timestamp("2020-02-14")
        nav_exec_gross = manifest.portfolio.initial_capital_usd
        sh = {s: nav_exec_gross * w / r.fill_prices[s] for s, w in r.weights.items()}
        cash = nav_exec_gross * (1.0 - sum(r.weights.values())) - r.cost_usd
        atteso = cash + sh["ZMISS"] * ds.close.loc[d, "ZMISS"] + sh["ZGONE"] * ds.close.loc[d, "ZGONE"] * 0.6
        assert res.nav.loc[d] == pytest.approx(atteso, rel=1e-9)

    def test_missing_status_fail_closed(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = hand_dataset(delistings=(("ZMISS", date(2020, 2, 14), -0.5, True),))
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-07-31"))
        assert res.decision_grade is False
        assert len(res.unresolved_delistings) == 1
        u = res.unresolved_delistings[0]
        assert u["security_id"] == "ZMISS"
        assert u["delisting_date"] == pd.Timestamp("2020-02-14")

    def test_dopo_delisting_il_mese_successivo_non_lo_pesa(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = hand_dataset(delistings=(("ZGONE", date(2020, 2, 14), -1.0, False),))
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-07-31"))
        dopo = [r for r in res.rebalances if r.signal_date > pd.Timestamp("2020-02-14")]
        assert dopo
        for r in dopo:
            assert "ZGONE" not in r.weights


class TestCosti:
    def test_composizione_dal_manifest_al_primo_riporto(self, manifest) -> None:
        """Il costo del primo ribilancio e' esattamente half-spread + impact
        sqrt + commissioni sui buy, con i parametri del manifest congelato."""
        from src.backtest.costs.impact_model import SquareRootImpactModel
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r = res.rebalances[0]
        assert r.cost_usd > 0
        impact = SquareRootImpactModel(k=manifest.costs.impact_k)
        # ordini del primo ribilancio = valore target per nome al prezzo di fill
        nav_exec_gross = manifest.portfolio.initial_capital_usd
        atteso = 0.0
        for sec, price in r.fill_prices.items():
            order_usd = nav_exec_gross * r.weights[sec]
            adv = float((ds.close[sec] * ds.volume[sec]).loc[: r.signal_date].tail(20).mean())
            bps = manifest.costs.spread_bps / 2 + impact.impact_bps(order_usd, adv)
            atteso += order_usd * bps / 1e4 + manifest.costs.commission_per_share * (order_usd / price)
        assert r.cost_usd == pytest.approx(atteso, rel=1e-6)

    def test_scenario_due_volte_raddoppia_i_costi(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = drift_dataset()
        base = run_sleeve(ds, manifest, variant="B",
                          start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-06-30"))
        doppio = run_sleeve(ds, manifest, variant="B",
                            start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-06-30"),
                            cost_multiplier=2.0)
        assert len(base.rebalances) == len(doppio.rebalances)
        # primo ribilancio: taglie identiche, raddoppio esatto
        assert doppio.rebalances[0].cost_usd == pytest.approx(2.0 * base.rebalances[0].cost_usd, rel=1e-9)
        for rb, rd in zip(base.rebalances, doppio.rebalances):
            assert rb.signal_date == rd.signal_date
            assert rb.selected == rd.selected
            assert rd.cost_usd > rb.cost_usd
        # il NAV sconta i costi extra
        ultimo = base.nav.index[-1]
        assert doppio.nav.loc[ultimo] < base.nav.loc[ultimo]

    def test_lo_spread_viene_dal_manifest(self, manifest, tmp_path_factory) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        m20 = manifest
        m40 = load_manifest(write_manifest_override(
            tmp_path_factory.mktemp("m40"), {"universe": {"min_breadth": 3}, "costs": {"spread_bps": 40.0}}
        ))
        ds = drift_dataset()
        kw = dict(variant="B", start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-03-31"))
        r20 = run_sleeve(ds, m20, **kw).rebalances[0]
        r40 = run_sleeve(ds, m40, **kw).rebalances[0]
        # half-spread 10 -> 20 bps: il delta e' il notionale x 10bps, commissioni e impact invariati
        notional = sum(m20.portfolio.initial_capital_usd * w
                       for w in r20.weights.values())
        assert r40.cost_usd - r20.cost_usd == pytest.approx(notional * 10.0 / 1e4, rel=1e-6)


class TestBreadthInsufficiente:
    def test_mese_sotto_breadth_in_cassa(self, tmp_path_factory) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        m = load_manifest(write_manifest_override(
            tmp_path_factory.mktemp("mb"), {"universe": {"min_breadth": 200}}
        ))
        ds = drift_dataset()
        res = run_sleeve(ds, m, variant="B",
                         start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-04-30"))
        assert res.rebalances
        for r in res.rebalances:
            assert r.breadth_sufficient is False
            assert r.weights == {}
            assert r.selected == ()
        assert res.months_in_cash == len(res.rebalances)
        # nessun trade: NAV fermo al capitale iniziale
        assert res.nav.nunique() == 1
        assert res.nav.iloc[0] == pytest.approx(m.portfolio.initial_capital_usd)
        assert res.decision_grade is True


class TestWalkForward:
    @pytest.fixture(scope="class")
    def lungo(self):
        return drift_dataset(start=date(2014, 1, 1), end=date(2021, 12, 31))

    def test_finestre_60_12_12_su_96_mesi(self, manifest, lungo) -> None:
        from src.analysis.s3_poc.engine import run_walk_forward, walk_forward_windows

        windows = walk_forward_windows(manifest, pd.Timestamp("2014-01-01"), pd.Timestamp("2021-12-31"))
        assert windows == [
            (pd.Timestamp("2019-01-01"), pd.Timestamp("2019-12-31")),
            (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")),
            (pd.Timestamp("2021-01-01"), pd.Timestamp("2021-12-31")),
        ]
        results = run_walk_forward(lungo, manifest, variant="B",
                                   period_start=pd.Timestamp("2014-01-01"),
                                   period_end=pd.Timestamp("2021-12-31"))
        assert [(r.start, r.end) for r in results] == windows

    def test_stato_fresco_e_invarianza_all_ordine(self, manifest, lungo) -> None:
        """Ogni finestra gira da sola, in qualunque ordine, con gli stessi
        risultati: lo stato della strategia non attraversa le finestre."""
        from src.analysis.s3_poc.engine import run_sleeve, run_walk_forward, walk_forward_windows

        windows = walk_forward_windows(manifest, pd.Timestamp("2014-01-01"), pd.Timestamp("2021-12-31"))
        intere = run_walk_forward(lungo, manifest, variant="B",
                                  period_start=pd.Timestamp("2014-01-01"),
                                  period_end=pd.Timestamp("2021-12-31"))
        for (ws, we), intera in zip(reversed(windows), reversed(intere)):
            sola = run_sleeve(lungo, manifest, variant="B", start=ws, end=we)
            pd.testing.assert_series_equal(sola.nav, intera.nav)
            assert sola.rebalances == intera.rebalances

    def test_finestre_derivate_dal_manifest(self, tmp_path_factory, lungo) -> None:
        from src.analysis.s3_poc.engine import walk_forward_windows

        m = load_manifest(write_manifest_override(
            tmp_path_factory.mktemp("wf"), {"walkforward": {"in_sample_months": 24}}
        ))
        windows = walk_forward_windows(m, pd.Timestamp("2014-01-01"), pd.Timestamp("2021-12-31"))
        assert windows[0][0] == pd.Timestamp("2016-01-01")
        assert len(windows) == 6


def rotation_dataset(
    jump_index: int = 380,
    open_ratio: float = 0.9,
    start: date = date(2018, 1, 1),
    end: date = date(2021, 12, 31),
):
    """Dataset craftato in cui il decile alto ruota davvero.

    Undici security identici piu' ``AAROT``, che raddoppia una volta sola
    alla seduta ``jump_index``. Finche' il salto sta dentro la finestra
    12-1 AAROT e' il primo per momentum ed entra; quando il salto esce
    dalla finestra torna in parita' e, essendo il primo in ordine
    alfabetico, esce dal decile. Ogni open e' ``open_ratio`` volte il
    close della stessa seduta: un fill all'open e uno al close sono quindi
    distinguibili al centesimo, su entrambi i lati.
    """
    from src.analysis.s3_poc.dataset import PitDataset, Provenance

    sessions = pd.bdate_range(start, end)
    n = len(sessions)
    base = pattern_prices(n)
    ids = [f"S{i:02d}" for i in range(11)] + ["AAROT"]
    close = pd.DataFrame({sec: base.copy() for sec in ids}, index=sessions)
    close["AAROT"] = base * np.where(np.arange(n) >= jump_index, 2.0, 1.0)
    prov = Provenance(
        vendor="hand", release="1", obtained_at=date(2026, 9, 16),
        files_sha256={}, synthetic=True, qualified=False, qualification_artifact=None,
    )
    return PitDataset(
        provenance=prov,
        close=close,
        open=close * open_ratio,
        volume=pd.DataFrame(1e6, index=sessions, columns=ids),
        market_cap=pd.DataFrame(1e10, index=sessions, columns=ids),
        open_reliable=pd.DataFrame(True, index=sessions, columns=ids),
        security_master=pd.DataFrame([
            {"security_id": sec, "valid_from": sessions[0], "valid_to": sessions[-1],
             "share_type": "common", "primary_exchange": "NYSE", "sector": "X"}
            for sec in ids
        ]),
        delistings=pd.DataFrame(
            columns=["security_id", "delisting_date", "delisting_return", "missing_status"]
        ),
        market=pd.Series(pattern_prices(n, 0.001), index=sessions),
    )


def primo_ribilancio_con_uscita(res) -> tuple[int, str]:
    """Indice del primo ribilancio che chiude una posizione, e il nome uscito."""
    for i in range(1, len(res.rebalances)):
        uscite = set(res.rebalances[i - 1].weights) - set(res.rebalances[i].weights)
        if uscite:
            return i, sorted(uscite)[0]
    raise AssertionError("il dataset non produce nessuna uscita dal decile")


class TestEsecuzioneLatoUscita:
    """Le uscite seguono la stessa regola congelata degli ingressi.

    Il manifest congela ``execution: next_session_open`` col close solo
    come fallback. Vendere al close della seduta in cui si compra all'open
    sarebbe una deviazione sistematica dalla regola pre-registrata, su ogni
    rotazione mensile: alimenta i gate standalone e il test combinato,
    cioe' la metrica decisionale.
    """

    def test_uscita_riempita_all_open_come_gli_ingressi(self, manifest) -> None:
        from src.analysis.s3_poc.engine import run_sleeve

        ds = rotation_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        i, uscito = primo_ribilancio_con_uscita(res)
        r = res.rebalances[i]
        d = r.execution_date
        assert uscito not in r.weights  # e' davvero una vendita a zero
        assert uscito in r.fill_prices
        assert r.fill_prices[uscito] == pytest.approx(ds.open.loc[d, uscito], rel=1e-12)
        assert r.fill_prices[uscito] != pytest.approx(ds.close.loc[d, uscito], rel=1e-6)

    def test_uscita_nel_notionale_al_prezzo_di_open(self, manifest) -> None:
        """Il notionale del ribilancio conta la vendita al prezzo di fill:
        le quantita' uscite valorizzate all'open, non al close."""
        from src.analysis.s3_poc.engine import run_sleeve

        ds = rotation_dataset()
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        i, uscito = primo_ribilancio_con_uscita(res)
        prec, r = res.rebalances[i - 1], res.rebalances[i]
        # quantita' detenuta all'uscita: il ribilancio precedente e' il primo
        # (nulla detenuto prima), quindi le azioni sono ricostruibili esatte
        assert i == 1
        nav0 = manifest.portfolio.initial_capital_usd
        qty = nav0 * prec.weights[uscito] / prec.fill_prices[uscito]
        venduto_open = qty * ds.open.loc[r.execution_date, uscito]
        venduto_close = qty * ds.close.loc[r.execution_date, uscito]
        # il notionale totale contiene la gamba di vendita all'open
        assert r.traded_notional_usd >= venduto_open
        assert r.traded_notional_usd < venduto_open + venduto_close

    def test_uscita_con_open_inaffidabile_usa_il_close(self, manifest) -> None:
        """Stesso fallback degli ingressi: open non affidabile -> close
        della stessa seduta di esecuzione, mai un close stantio."""
        from src.analysis.s3_poc.engine import run_sleeve

        ds = rotation_dataset()
        sonda = run_sleeve(ds, manifest, variant="B",
                           start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        i, uscito = primo_ribilancio_con_uscita(sonda)
        d = sonda.rebalances[i].execution_date
        ds.open_reliable.loc[d, uscito] = False
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        r = res.rebalances[i]
        assert r.fill_prices[uscito] == pytest.approx(ds.close.loc[d, uscito], rel=1e-12)

    def test_uscita_senza_prezzo_utilizzabile_resta_in_posizione(self, manifest) -> None:
        """Nessun prezzo di esecuzione -> il nome non si vende a un close
        stantio: resta in posizione e il ribilancio lo dichiara skippato."""
        from src.analysis.s3_poc.engine import run_sleeve

        ds = rotation_dataset()
        sonda = run_sleeve(ds, manifest, variant="B",
                           start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        i, uscito = primo_ribilancio_con_uscita(sonda)
        d = sonda.rebalances[i].execution_date
        ds.open.loc[d, uscito] = np.nan
        ds.close.loc[d, uscito] = np.nan
        res = run_sleeve(ds, manifest, variant="B",
                         start=pd.Timestamp("2019-06-01"), end=pd.Timestamp("2020-06-30"))
        r = res.rebalances[i]
        assert uscito in r.skipped_execution
        assert uscito not in r.fill_prices
        # e il mese dopo la posizione e' ancora li' da liquidare
        assert uscito not in res.rebalances[i + 1].weights
        assert uscito in res.rebalances[i + 1].fill_prices
