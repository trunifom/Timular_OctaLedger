"""Run the OctaLedger command-line interface (``python -m octaledger``)."""

import sys

from octaledger.cli import main

if __name__ == "__main__":
    sys.exit(main())
