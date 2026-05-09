"""Evaluate FUBON captcha OCR accuracy on fixture samples.

Usage: uv run python scripts/eval_captcha.py [--fixtures-dir PATH]

Loads all *.jpg files from the fixtures directory (filename stem = ground truth).
Reports accept rate and accuracy. Exits with code 1 if accuracy < 80%.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ccas.ingestor.fetcher.banks.fubon.captcha import solve

DEFAULT_FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "fubon"
    / "captcha_samples"
)
MIN_ACCURACY = 0.80


def evaluate(fixtures_dir: Path) -> int:
    samples = sorted(fixtures_dir.glob("*.jpg"))
    if not samples:
        print(f"No *.jpg files found in {fixtures_dir}")
        return 1

    accepted = 0
    correct = 0
    rejected = 0
    false_positives: list[str] = []

    for p in samples:
        gt = p.stem
        result = solve(p.read_bytes())
        if result is None:
            rejected += 1
        else:
            accepted += 1
            if result.text == gt:
                correct += 1
            else:
                false_positives.append(
                    f"  {p.name}: expected={gt} got={result.text} "
                    f"conf={result.confidence:.3f}"
                )

    total = len(samples)
    accept_rate = accepted / total if total else 0
    accuracy = correct / accepted if accepted else 0

    print(f"Samples:     {total}")
    print(f"Accepted:    {accepted} ({accept_rate:.1%})")
    print(f"Rejected:    {rejected}")
    print(f"Correct:     {correct}")
    print(f"Accuracy:    {accuracy:.1%} (of accepted)")
    print(f"Threshold:   {MIN_ACCURACY:.0%}")

    if false_positives:
        print(f"\nFalse positives ({len(false_positives)}):")
        for fp in false_positives:
            print(fp)

    if accuracy < MIN_ACCURACY:
        print(f"\nFAIL: accuracy {accuracy:.1%} < {MIN_ACCURACY:.0%}")
        return 1

    print("\nPASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FUBON captcha OCR accuracy")
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DEFAULT_FIXTURES,
        help="Captcha JPEG fixtures dir (stem = ground truth)",
    )
    args = parser.parse_args()
    sys.exit(evaluate(args.fixtures_dir))


if __name__ == "__main__":
    main()
