"""Offline actual frame6411 Hair/Eye descriptors; no live access or transcodes.

PS22257: HN/P/Base biased s4, Line implicit s4 + own ST, ramps LOD0 s6.
PS22259: Base biased s4, Matcap biased s6, DiffRamp LOD0 s6.
The collector checks real sampler descriptors; new manifests need review.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
import capture_cloth_materials as native

ROLES = {
    875: {"HN": 1, "SpecRamp": 2, "P": 3, "Line": 4, "DiffRamp": 5, "Base": 6},
    776: {"Matcap": 1, "DiffRamp": 2, "Base": 3},
}
PROGRAMS = {875: 22257, 776: 22259}
SAMPLERS = {
    "HN": 4,
    "SpecRamp": 6,
    "P": 4,
    "Line": 4,
    "DiffRamp": 6,
    "Base": 4,
    "Matcap": 6,
}


def run():
    return native.run(ROLES, PROGRAMS, SAMPLERS)


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
