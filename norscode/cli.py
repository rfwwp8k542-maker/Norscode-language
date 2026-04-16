from main import main
import os
import sys


def _warn_legacy_cli():
    if os.environ.get("NORSCODE_SUPPRESS_LEGACY_WARNING") == "1":
        return
    print(
        "Legacy warning: python-modus er i avvikling. Bruk `norscode` eller `bin/nc` for primær binær-first flyt.",
        file=sys.stderr,
    )


def main_cli():
    _warn_legacy_cli()
    main()
