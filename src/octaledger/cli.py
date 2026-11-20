"""Command-line diagnostics; no BLE transport is implemented yet."""

import argparse

from octaledger import __version__
from octaledger.domain.orientation import decode_orientation


def main() -> None:
    """Parse scaffold commands."""
    parser = argparse.ArgumentParser(description="OctaLedger development scaffold")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--decode-test", type=int, choices=range(9), metavar="0..8")
    args = parser.parse_args()
    if args.decode_test is not None:
        print(f"Test input, not hardware: {decode_orientation(bytes([args.decode_test]))}")
    else:
        parser.print_help()
