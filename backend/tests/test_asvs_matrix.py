"""Keep the documented ASVS Level 2 scope pinned to the official 5.0.0 CSV."""

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
SOURCE = DOCS / "ASVS_5.0.0_SOURCE.csv"
MATRIX = DOCS / "ASVS_5.0.0_L2_MATRIX.md"
SOURCE_SHA256 = "98c8fe911b9edb403af8ee05d3ce8201ecac2659e313b053890a62847cdcf680"


def test_asvs_matrix_has_every_l1_and_l2_requirement_once():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256
    with SOURCE.open(newline="") as handle:
        source = [row for row in csv.DictReader(handle) if row["L"] in {"1", "2"}]
    expected = {(row["req_id"], row["L"]) for row in source}
    assert len(source) == len(expected) == 253
    assert Counter(row["L"] for row in source) == {"1": 70, "2": 183}

    rows = re.findall(
        r"^\| (V\d+\.\d+\.\d+) \(ASVS 5\.0\.0 L([12])\) \| ([^|]+) \| (.+) \|$",
        MATRIX.read_text(),
        re.MULTILINE,
    )
    actual = [(identifier, level) for identifier, level, _, _ in rows]
    assert len(actual) == len(set(actual)) == 253
    assert set(actual) == expected
    assert all(
        status in {"Potwierdzone", "Częściowo", "Brak", "N/D", "Nieocenione"} and evidence.strip()
        for _, _, status, evidence in rows
    )
