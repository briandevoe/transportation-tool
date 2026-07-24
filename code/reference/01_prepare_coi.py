"""
Reference data: standardize the Child Opportunity Index (COI 3.0-2021) into
a small GEOID-keyed lookup table.

Source: data/reference/coi/2020 census tracts, overall index and domains
(COI 3.0-2021).zip -> data.csv. One row per (geoid20, year) covering
2012-2021 (confirmed live) -- this script keeps one year, default the most
recent (2021).

geoid20 is already a 2020 census tract GEOID -- a direct join key, no
crosswalk needed (unlike redlining -- see 03_prepare_redlining.py).

Usage:
    python 01_prepare_coi.py                 # 2021 (default, most recent)
    python 01_prepare_coi.py --year 2015
"""
import argparse
import zipfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "reference" / "coi"
OUT_DIR = DATA_DIR / "processed"

SOURCE_ZIP = "2020 census tracts, overall index and domains (COI 3.0-2021).zip"

COLUMN_MAP = {
    "geoid20": "GEOID",
    "c5_COI_nat": "coi_level_nat",
    "r_COI_nat": "coi_score_nat",
    "c5_COI_stt": "coi_level_stt",
    "r_COI_stt": "coi_score_stt",
    "c5_COI_met": "coi_level_met",
    "r_COI_met": "coi_score_met",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2021, help="COI vintage year, 2012-2021 (default: 2021)")
    args = parser.parse_args()

    zip_path = DATA_DIR / SOURCE_ZIP
    if not zip_path.exists():
        raise SystemExit(f"Missing {zip_path}")

    print(f"Reading {zip_path.name}...")
    with zipfile.ZipFile(zip_path) as z:
        with z.open("data.csv") as f:
            df = pd.read_csv(f, usecols=list(COLUMN_MAP) + ["year"], dtype={"geoid20": str}, low_memory=False)

    before = len(df)
    df = df[df["year"] == args.year].drop(columns="year")
    print(f"  {len(df):,} tracts for year {args.year} (of {before:,} total rows across all years)")

    df = df.rename(columns=COLUMN_MAP)
    for col in ["coi_level_nat", "coi_level_stt", "coi_level_met"]:
        df[col] = df[col].astype("string")
    for col in ["coi_score_nat", "coi_score_stt", "coi_score_met"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["GEOID"] = df["GEOID"].astype("string")
    df["coi_vintage"] = str(args.year)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"coi_tract_{args.year}.parquet"
    df.to_parquet(out_path)
    print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
