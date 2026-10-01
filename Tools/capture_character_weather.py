"""Offline frame6411 cloth weather inputs, not a wet-weather capture certificate.

Actual PS22255: set0/t44 rain effect, t41 streak, both s4 (Repeat).
Retains native views, all mip bytes and independent typed pixel samples.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)

from capture_cloth_materials import run

if __name__ == "__main__":
    exit_code = 1
    try:
        run(
            {835: {"Rain": 44, "Streak": 41}}, {835: 22255}, {"Rain": 4, "Streak": 4}, 0
        )
        exit_code = 0
    finally:
        # run() writes error.json and shuts down replay handles on exceptions.
        # Do not let the explicit host shutdown turn a failed export into exit 0.
        sys.exit(exit_code)
