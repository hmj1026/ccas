"""Evaluate FUBON captcha OCR accuracy on fixture samples.

Usage: uv run python scripts/eval_captcha.py [--fixtures-dir PATH]

Loads all *.jpg files from the fixtures directory (filename stem = ground truth).
Reports accept rate and accuracy. Exits with code 1 if accept rate or accuracy
is below 80%, or if any accepted result is incorrect.
"""

from __future__ import annotations

import argparse
import logging
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
MIN_ACCEPT_RATE = 0.80


def evaluate(fixtures_dir: Path, verbose: bool = False) -> int:
    samples = sorted(fixtures_dir.glob("*.jpg"))
    if not samples:
        print(f"No *.jpg files found in {fixtures_dir}")
        return 1

    accepted = 0
    correct = 0
    rejected = 0
    false_positives: list[str] = []
    rejected_samples: list[str] = []

    for p in samples:
        gt = p.stem
        result = solve(p.read_bytes())
        if result is None:
            rejected += 1
            if len(rejected_samples) < 5:
                rejected_samples.append(f"{p.name} (ground truth={gt})")
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
    print(
        f"Threshold:   accept rate >= {MIN_ACCEPT_RATE:.0%}, "
        f"accuracy >= {MIN_ACCURACY:.0%}, false positives = 0"
    )

    if false_positives:
        print(f"\nFalse positives ({len(false_positives)}):")
        for fp in false_positives:
            print(fp)

    if rejected_samples:
        print(f"\nRejected samples preview (first {len(rejected_samples)}):")
        for r in rejected_samples:
            print(f"  {r}")

    failed = False
    if accept_rate < MIN_ACCEPT_RATE:
        print(f"\nFAIL: accept rate {accept_rate:.1%} < {MIN_ACCEPT_RATE:.0%}")
        failed = True
    if accuracy < MIN_ACCURACY:
        print(f"\nFAIL: accuracy {accuracy:.1%} < {MIN_ACCURACY:.0%}")
        failed = True
    if false_positives:
        print(f"\nFAIL: false positives {len(false_positives)} > 0")
        failed = True

    if failed:
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    sys.exit(evaluate(args.fixtures_dir, verbose=args.verbose))


if __name__ == "__main__":
    main()
