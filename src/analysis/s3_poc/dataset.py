"""Contratto del dataset PIT del POC S3 e gate di qualificazione.

Il dataset e' la sola entrata dati del runner: prezzi daily total-return,
anagrafica con intervalli di validita', market cap PIT, delisting con
rendimento economico. Un dataset reale e' utilizzabile solo se il gate dati
(#84, fase 0) e' stato riaperto in GO: la regola di stop e' applicata qui.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


class DatasetError(ValueError):
    """Il dataset viola lo schema del POC."""


class DatasetNotQualified(RuntimeError):
    """Dataset reale senza GO del gate dati: il run non puo' partire."""


LONG_COLUMNS = [
    "date", "security_id", "open", "close", "volume", "market_cap", "open_reliable",
]


@dataclass(frozen=True)
class Provenance:
    vendor: str
    release: str
    obtained_at: date
    files_sha256: dict[str, str]
    synthetic: bool
    qualified: bool
    qualification_artifact: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "release": self.release,
            "obtained_at": self.obtained_at.isoformat(),
            "files_sha256": self.files_sha256,
            "synthetic": self.synthetic,
            "qualified": self.qualified,
            "qualification_artifact": self.qualification_artifact,
        }


@dataclass(frozen=True)
class PitDataset:
    """Dataset PIT in frame wide allineati sulle sedute.

    close/open sono prezzi total-return (split+dividendi), come congelato nel
    manifest: segnale ed esecuzione usano la stessa base di aggiustamento.
    open_reliable e' il flag del vendor che autorizza l'esecuzione all'open.
    """

    provenance: Provenance
    close: pd.DataFrame
    open: pd.DataFrame
    volume: pd.DataFrame
    market_cap: pd.DataFrame
    open_reliable: pd.DataFrame
    security_master: pd.DataFrame
    delistings: pd.DataFrame
    market: pd.Series

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.close.index)

    def with_provenance(self, provenance: Provenance) -> "PitDataset":
        return replace(self, provenance=provenance)

    def truncate_at(self, as_of: pd.Timestamp) -> "PitDataset":
        """Copia del dataset come appariva a `as_of`: nessuna riga futura.

        Le righe daily e il mercato si troncano a <= as_of; i delisting
        successivi ad as_of sono sconosciuti e cadono; gli intervalli
        dell'anagrafica si tagliano ad as_of. Serve ai test di leakage.
        """
        as_of = pd.Timestamp(as_of)
        master = self.security_master.copy()
        master["valid_to"] = pd.to_datetime(master["valid_to"]).clip(upper=as_of)
        delistings = self.delistings[
            pd.to_datetime(self.delistings["delisting_date"]) <= as_of
        ]
        return replace(
            self,
            close=self.close.loc[self.close.index <= as_of],
            open=self.open.loc[self.open.index <= as_of],
            volume=self.volume.loc[self.volume.index <= as_of],
            market_cap=self.market_cap.loc[self.market_cap.index <= as_of],
            open_reliable=self.open_reliable.loc[self.open_reliable.index <= as_of],
            market=self.market.loc[self.market.index <= as_of],
            security_master=master,
            delistings=delistings,
        )

    def to_long(self) -> pd.DataFrame:
        close = self.close.stack().rename("close")
        frames = {
            "open": self.open,
            "volume": self.volume,
            "market_cap": self.market_cap,
            "open_reliable": self.open_reliable,
        }
        long_df = close.reset_index()
        long_df.columns = ["date", "security_id", "close"]
        for name, frame in frames.items():
            values = frame.stack().rename(name).reset_index()
            values.columns = ["date", "security_id", name]
            long_df = long_df.merge(values, on=["date", "security_id"], how="left")
        return long_df[LONG_COLUMNS]

    @staticmethod
    def from_long(
        long_df: pd.DataFrame,
        security_master: pd.DataFrame,
        delistings: pd.DataFrame,
        market: pd.Series,
        provenance: Provenance,
    ) -> "PitDataset":
        missing = set(LONG_COLUMNS) - set(long_df.columns)
        if missing:
            raise DatasetError(f"colonne mancanti nel daily: {sorted(missing)}")
        dup = long_df.duplicated(subset=["date", "security_id"])
        if dup.any():
            raise DatasetError(
                f"righe duplicate (date, security_id): {int(dup.sum())}"
            )
        if (long_df["close"] <= 0).any():
            raise DatasetError("prezzi close non positivi")

        index = pd.DatetimeIndex(pd.to_datetime(long_df["date"]).sort_values().unique())

        def wide(column: str) -> pd.DataFrame:
            pivot = long_df.pivot(index="date", columns="security_id", values=column)
            pivot.index = pd.DatetimeIndex(pd.to_datetime(pivot.index))
            pivot.columns.name = None  # allineato ai frame del builder sintetico
            return pivot.sort_index().reindex(index)

        return PitDataset(
            provenance=provenance,
            close=wide("close"),
            open=wide("open"),
            volume=wide("volume"),
            market_cap=wide("market_cap"),
            open_reliable=wide("open_reliable").fillna(False).astype(bool),
            security_master=security_master,
            delistings=delistings,
            market=market.sort_index(),
        )

    @staticmethod
    def to_directory(ds: "PitDataset", directory: Path | str) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        ds.to_long().to_parquet(directory / "daily.parquet", index=False)
        ds.security_master.to_parquet(directory / "security_master.parquet", index=False)
        ds.delistings.to_parquet(directory / "delistings.parquet", index=False)
        ds.market.rename("market").to_frame().to_parquet(directory / "market.parquet")
        (directory / "provenance.json").write_text(
            json.dumps(ds.provenance.to_dict(), indent=2)
        )

    @staticmethod
    def from_directory(directory: Path | str) -> "PitDataset":
        directory = Path(directory)
        long_df = pd.read_parquet(directory / "daily.parquet")
        security_master = pd.read_parquet(directory / "security_master.parquet")
        delistings = pd.read_parquet(directory / "delistings.parquet")
        market = pd.read_parquet(directory / "market.parquet")["market"]
        prov_raw = json.loads((directory / "provenance.json").read_text())
        provenance = Provenance(
            vendor=prov_raw["vendor"],
            release=prov_raw["release"],
            obtained_at=date.fromisoformat(prov_raw["obtained_at"]),
            files_sha256=prov_raw["files_sha256"],
            synthetic=prov_raw["synthetic"],
            qualified=prov_raw["qualified"],
            qualification_artifact=prov_raw["qualification_artifact"],
        )
        return PitDataset.from_long(long_df, security_master, delistings, market, provenance)


def canonical_sha256(ds: PitDataset) -> str:
    """Hash deterministico dei frame: stessa identita' dei dati, stesso hash."""
    digest = hashlib.sha256()
    for frame in (ds.close, ds.open, ds.volume, ds.market_cap, ds.open_reliable):
        digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    digest.update(pd.util.hash_pandas_object(ds.market, index=True).values.tobytes())
    for frame in (ds.security_master, ds.delistings):
        digest.update(pd.util.hash_pandas_object(frame, index=False).values.tobytes())
    return digest.hexdigest()


def require_qualified_or_synthetic(ds: PitDataset, qualification_required: bool) -> None:
    """Regola di stop del gate dati: run reali solo con GO documentato."""
    if not qualification_required or ds.provenance.synthetic:
        return
    if not ds.provenance.qualified or not ds.provenance.qualification_artifact:
        raise DatasetNotQualified(
            "dataset reale senza qualificazione GO del gate dati "
            "(docs/RESEARCH_S3_PIT_DATA_FEASIBILITY_2026-07-21.md): run rifiutato"
        )
    if not Path(ds.provenance.qualification_artifact).exists():
        raise DatasetNotQualified(
            f"artefatto di qualificazione assente: {ds.provenance.qualification_artifact}"
        )
