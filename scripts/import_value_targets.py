from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.telegram_bot import _save_value_bulk


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import valuation target rows in 'ticker / name / market / fair / buy / currency / notes' format."
    )
    parser.add_argument("path", nargs="?", help="Input text file. Reads stdin when omitted.")
    args = parser.parse_args()

    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    print(_save_value_bulk(text))


if __name__ == "__main__":
    main()
