"""Keep native speech libraries out of the desktop server process."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from .optional_setup import activate_installed
from .speech import SpeechError, transcribe


def main() -> int:
    activate_installed()
    try:
        result = transcribe(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    except SpeechError as error:
        print(json.dumps({"error": str(error)}), flush=True)
        return 1
    print(json.dumps({"result": result}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
