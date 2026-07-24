"""
Reference data: standardize 2020 RUCA (Rural-Urban Commuting Area) codes
into a small GEOID-keyed lookup table.

Source: data/layer5_reference/ruca/RUCA-codes-2020-tract.csv -- one row per tract,
TractFIPS20 is a direct 2020 census tract GEOID join key.

Usage:
    python 02_prepare_ruca.py
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
SOURCE_CSV = REPO_ROOT / "data" / "layer5_reference" / "ruca" / "RUCA-codes-2020-tract.csv"
OUT_DIR = REPO_ROOT / "data" / "layer5_reference" / "ruca" / "processed"

COLUMN_MAP = {
    "TractFIPS20": "GEOID",
    "PrimaryRUCA": "ruca_code",
    "PrimaryRUCADescription": "ruca_description",
}


def main():
    if not SOURCE_CSV.exists():
        raise SystemExit(f"Missing {SOURCE_CSV}")

    print(f"Reading {SOURCE_CSV.name}...")
    df = pd.read_csv(SOURCE_CSV, usecols=list(COLUMN_MAP), dtype={"TractFIPS20": str}, encoding="cp1252")
    df = df.rename(columns=COLUMN_MAP)

    df["GEOID"] = df["GEOID"].astype("string")
    df["ruca_code"] = pd.to_numeric(df["ruca_code"], errors="coerce")
    df["ruca_description"] = df["ruca_description"].astype("string")
    df["ruca_vintage"] = "2020"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "ruca_tract_2020.parquet"
    df.to_parquet(out_path)
    print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
