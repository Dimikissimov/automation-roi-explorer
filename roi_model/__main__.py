"""__main__.py — enables ``python -m roi_model`` to run the CLI.

Usage:
    python -m roi_model
"""

import sys

from roi_model.cli import main

if __name__ == "__main__":
    sys.exit(main())
