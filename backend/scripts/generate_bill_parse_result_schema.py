"""Generate the checked-in JSON Schema for bill parse results."""

import json
from pathlib import Path

from ccas.parser.result_schema import BillParseResultSchema


def main() -> None:
    output = (
        Path(__file__).resolve().parents[2] / "schemas/bill_parse_result.schema.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            BillParseResultSchema.model_json_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
