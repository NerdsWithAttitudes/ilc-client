#!/usr/bin/env python3
"""Build the deterministic executable benchmark fixture."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    fixture_path = root / "src" / "ilc" / "executable" / "fixtures" / "mnist_v1.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    images = [
        [round(((row + 1) * (col + 3) % 29 - 14) / 32.0, 6) for col in range(65)]
        for row in range(16)
    ]
    weights = [
        [round(((row + 5) * (col + 7) % 31 - 15) / 64.0, 6) for col in range(10)]
        for row in range(65)
    ]
    labels = [(idx * 7) % 10 for idx in range(16)]
    fixture_path.write_text(
        json.dumps({"images": images, "weights": weights, "labels": labels}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

