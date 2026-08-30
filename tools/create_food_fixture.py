from __future__ import annotations

"""Create the deterministic binary fixture used by file-feeding tests."""

import argparse
from pathlib import Path


def fixture_bytes() -> bytes:
    # Binary bytes, not a text/HEX encoding: recurring local motifs plus all
    # byte values exercise direct 0..255 digestion while remaining viable.
    motif = bytes((0x41, 0x42, 0x41, 0x42, 0xC3, 0x19, 0xC3, 0x19))
    return motif * 2048 + bytes(range(256)) * 8


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(fixture_bytes())
    print(f"wrote {args.output} ({len(fixture_bytes())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
