"""Offline actual frame6411 Skin body/face descriptors; reuse native exporter.

No live access or transcodes. A new complete manifest requires review before use.
Actual PS22250/37671: s4 Repeat biased Base/N/Emotion/Highlight; s6 Clamp
biased SDFMask and explicit-LOD0 ShadowLUT/DiffRamp/SDF.
"""

import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.environ.get("ENDFIELD_TOOLS_PATH") or str(Path(__file__).resolve().parent)
)
import capture_cloth_materials as native

ROLES = {
    786: {"ShadowLUT": 1, "DiffRamp": 2, "Normal": 3, "Base": 4},
    860: {
        "ShadowLUT": 1,
        "SDFMask": 2,
        "SDF": 3,
        "Highlight": 4,
        "Emotion": 5,
        "DiffRamp": 6,
        "Normal": 7,
        "Base": 8,
    },
}
PROGRAMS = {786: 22250, 860: 37671}
SAMPLERS = {
    "ShadowLUT": 6,
    "DiffRamp": 6,
    "Normal": 4,
    "Base": 4,
    "SDFMask": 6,
    "SDF": 6,
    "Highlight": 4,
    "Emotion": 4,
}


def run():
    return native.run(ROLES, PROGRAMS, SAMPLERS)


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit()
