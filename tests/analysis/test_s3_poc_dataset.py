"""Contratto del dataset PIT del POC S3 (#84) e del builder sintetico dorato.

Il dataset e' l'unico ingresso dati del runner. Un dataset reale senza la
qualificazione del gate dati (GO del vendor) non deve poter alimentare un run:
la regola di stop della preregistrazione e' codice, non buona volontà.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.dataset import (
    DatasetError,
    DatasetNotQualified,
    PitDataset,
    Provenance,
    require_qualified_or_synthetic,
)
from src.analysis.s3_poc.synthetic import SecuritySpec, SyntheticSpec, build_synthetic_dataset


def base_spec(**kwargs) -> SyntheticSpec:
    defaults = dict(
        start=date(2020, 1, 1),
        end=date(2021, 12, 31),
        securities=tuple(
            SecuritySpec(security_id=f"S{i:03d}", start_price=50.0 + i)
            for i in range(12)
        ),
    )
    defaults.update(kwargs)
    return SyntheticSpec(**defaults)


class TestDatasetSintetico:
    def test_provenanza_sintetica_e_hash_deterministico(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        assert ds.provenance.synthetic is True
        assert ds.provenance.qualified is False
        ds2 = build_synthetic_dataset(base_spec())
        assert ds.provenance.files_sha256 == ds2.provenance.files_sha256
        assert ds.provenance.files_sha256  # non vuoto

    def test_frame_wide_allineati(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        sessions = pd.bdate_range("2020-01-01", "2021-12-31")
        assert list(ds.close.index) == list(sessions)
        assert set(ds.close.columns) == {f"S{i:03d}" for i in range(12)}
        for frame in (ds.open, ds.volume, ds.market_cap):
            assert frame.shape == ds.close.shape
        assert ds.open_reliable.shape == ds.close.shape
        # NaN fuori dalle sedute attive; valori solo booleani dove c'e' dato
        valori = set(pd.unique(ds.open_reliable.values.ravel()))
        assert valori.issubset({True, False, np.nan})
        assert isinstance(ds.market, pd.Series)
        assert ds.market.index.equals(ds.close.index)

    def test_un_security_inizia_dopo_e_ha_nan_prima(self) -> None:
        spec = base_spec(securities=(
            SecuritySpec(security_id="LATE", start=date(2021, 6, 1)),
            *base_spec().securities[:4],
        ))
        ds = build_synthetic_dataset(spec)
        assert ds.close.loc[: pd.Timestamp("2021-05-31"), "LATE"].isna().all()
        assert ds.close.loc[:, "LATE"].notna().any()

    def test_delisting_economico_riportato(self) -> None:
        spec = base_spec(securities=(
            SecuritySpec(security_id="BUST", delisting_date=date(2021, 3, 15), delisting_return=-1.0),
            SecuritySpec(
                security_id="CASHACQ", delisting_date=date(2021, 8, 2), delisting_return=0.30
            ),
            *base_spec().securities[:4],
        ))
        ds = build_synthetic_dataset(spec)
        dl = ds.delistings.set_index("security_id")
        assert dl.loc["BUST", "delisting_return"] == -1.0
        assert dl.loc["CASHACQ", "delisting_return"] == 0.30
        # nessuna quotazione dopo la data di delisting
        assert ds.close.loc[pd.Timestamp("2021-03-16"):, "BUST"].isna().all()

    def test_security_master_con_intervalli(self) -> None:
        spec = base_spec()
        ds = build_synthetic_dataset(spec)
        row = ds.security_master.set_index("security_id").loc["S000"]
        assert row["share_type"] == "common"
        assert row["primary_exchange"] == "NYSE"
        assert set(ds.security_master.columns) >= {
            "security_id", "valid_from", "valid_to", "share_type", "primary_exchange", "sector"
        }

    def test_open_non_affidabile_iniettabile(self) -> None:
        spec = base_spec(securities=(
            SecuritySpec(security_id="BADOPEN", open_unreliable_from=date(2021, 1, 4)),
            *base_spec().securities[:4],
        ))
        ds = build_synthetic_dataset(spec)
        prima = ds.open_reliable.loc[: pd.Timestamp("2021-01-03"), "BADOPEN"]
        dopo = ds.open_reliable.loc[pd.Timestamp("2021-01-04"):, "BADOPEN"]
        assert prima.all() and not dopo.any()

    def test_prezzi_positivi_e_volume_positivo(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        assert (ds.close.stack() > 0).all()
        assert (ds.volume.fillna(0).stack() >= 0).all()


class TestValidazioneDataset:
    def _long(self, ds: PitDataset) -> pd.DataFrame:
        return ds.to_long()

    def test_duplicati_rifiutati(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        long_df = self._long(ds)
        long_df = pd.concat([long_df, long_df.iloc[[0]]])
        with pytest.raises(DatasetError, match="duplicat"):
            PitDataset.from_long(
                long_df, ds.security_master, ds.delistings, ds.market, ds.provenance
            )

    def test_colonna_mancante_rifiutata(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        long_df = self._long(ds).drop(columns=["market_cap"])
        with pytest.raises(DatasetError, match="market_cap"):
            PitDataset.from_long(
                long_df, ds.security_master, ds.delistings, ds.market, ds.provenance
            )

    def test_roundtrip_da_disco(self, tmp_path) -> None:
        ds = build_synthetic_dataset(base_spec())
        PitDataset.to_directory(ds, tmp_path)
        loaded = PitDataset.from_directory(tmp_path)
        pd.testing.assert_frame_equal(loaded.close, ds.close, check_freq=False)
        assert loaded.provenance == ds.provenance


class TestGateDiQualificazione:
    def test_sintetico_passa(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        require_qualified_or_synthetic(ds, qualification_required=True)  # non solleva

    def test_reale_non_qualificato_rifiutato(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        real = ds.with_provenance(Provenance(
            vendor="crsp", release="2026-01", obtained_at=date(2026, 9, 16),
            files_sha256=ds.provenance.files_sha256, synthetic=False,
            qualified=False, qualification_artifact=None,
        ))
        with pytest.raises(DatasetNotQualified):
            require_qualified_or_synthetic(real, qualification_required=True)

    def test_reale_qualificato_con_artefatto_passa(self, tmp_path) -> None:
        ds = build_synthetic_dataset(base_spec())
        artifact = tmp_path / "gate.json"
        artifact.write_text(json.dumps({"verdict": "GO", "vendor": "crsp"}))
        real = ds.with_provenance(Provenance(
            vendor="crsp", release="2026-01", obtained_at=date(2026, 9, 16),
            files_sha256=ds.provenance.files_sha256, synthetic=False,
            qualified=True, qualification_artifact=str(artifact),
        ))
        require_qualified_or_synthetic(real, qualification_required=True)  # non solleva

    def test_qualifica_richiesta_false_lascia_passare(self) -> None:
        ds = build_synthetic_dataset(base_spec())
        real = ds.with_provenance(Provenance(
            vendor="x", release="1", obtained_at=date(2026, 9, 16),
            files_sha256=ds.provenance.files_sha256, synthetic=False,
            qualified=False, qualification_artifact=None,
        ))
        require_qualified_or_synthetic(real, qualification_required=False)  # non solleva


class TestNienteLeakageDalBuilder:
    def test_un_cambio_futuro_non_cambia_il_passato(self) -> None:
        """Il builder genera storicamente: aggiungere un security nuovo non
        tocca le serie degli altri (preparazione ai test di leakage veri)."""
        base = base_spec()
        ds1 = build_synthetic_dataset(base)
        ds2 = build_synthetic_dataset(SyntheticSpec(
            start=base.start, end=base.end,
            securities=base.securities + (SecuritySpec(security_id="EXTRA"),),
        ))
        pd.testing.assert_series_equal(
            ds1.close["S000"], ds2.close["S000"], check_names=False
        )
        # il seed controlla il mercato: serie identiche finche' lo spec e' lo stesso
        pd.testing.assert_series_equal(ds1.market, ds2.market)
