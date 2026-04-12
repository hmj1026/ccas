"""Harvest real FUBON captcha samples for OCR evaluation.

Connects to the FUBON SPA, fetches captcha images in a loop, and saves them
with OCR-predicted filenames. Requires a valid serial_key from a recent
FUBON bill email.

Usage:
    uv run python scripts/harvest_captcha.py <key> [--count 40]

After harvesting, manually verify filenames match the actual captcha text.
Delete or rename any mismatches before running eval_captcha.py.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from ccas.ingestor.fetcher.banks.fubon.captcha import solve
from ccas.ingestor.fetcher.banks.fubon.client import FubonClient

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "fubon"
    / "captcha_samples"
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def harvest(serial_key: str, count: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    fetched = 0
    saved = 0
    rejected = 0
    skipped = 0

    async with FubonClient() as client:
        await client.open_spa(serial_key=serial_key)
        logger.info("Session established. Fetching %d captchas...", count)

        for i in range(1, count + 1):
            try:
                _token, jpeg = await client.get_captcha()
                fetched += 1
            except Exception as exc:
                logger.warning("Fetch %d failed: %s", i, exc)
                continue

            result = solve(jpeg)
            if result is None:
                rejected += 1
                continue

            dest = output_dir / f"{result.text}.jpg"
            if dest.exists():
                skipped += 1
                continue

            dest.write_bytes(jpeg)
            saved += 1
            logger.info(
                "[%d/%d] Saved %s (conf=%.3f)",
                i, count, dest.name, result.confidence,
            )

    existing = len(list(output_dir.glob("*.jpg")))
    logger.info(
        "\nDone: fetched=%d saved=%d rejected=%d skipped=%d",
        fetched, saved, rejected, skipped,
    )
    logger.info("Total fixtures in %s: %d", output_dir, existing)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harvest FUBON captcha samples",
    )
    parser.add_argument(
        "serial_key",
        help="Valid serial key from a FUBON bill email",
    )
    parser.add_argument(
        "--count", type=int, default=40,
        help="Number of captchas to fetch (default: 40)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT,
        help="Output directory for JPEG files",
    )
    args = parser.parse_args()
    asyncio.run(harvest(args.serial_key, args.count, args.output_dir))


if __name__ == "__main__":
    main()
