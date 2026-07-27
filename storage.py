# -*- coding: utf-8 -*-
"""Вывод результатов в CSV (плоские файлы)."""
import csv
from datetime import datetime
from pathlib import Path

from config import RESULTS_DIR


def save_csv(results, region_code, marketplace, output_dir=None):
    if not results:
        return None
    out = Path(output_dir) if output_dir else RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = out / f"{marketplace}_{region_code}_{ts}.csv"
    keys = sorted({k for r in results for k in r.keys()})
    with open(fn, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in results:
            w.writerow(r)
    return str(fn)
