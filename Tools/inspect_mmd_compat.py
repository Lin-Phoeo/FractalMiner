"""Read-only PMX/VMD name coverage audit; does not copy or modify model data.

Requires pymeshio (https://github.com/ousttrue/pymeshio). For a portable
one-off install, use `uv pip install --target <dir> pymeshio` and pass that
directory with --reader-root. This tool checks name coverage, not pose quality.
"""

import argparse
import json
from pathlib import Path
import struct
import sys
import unicodedata


def vmd_tracks(path: Path) -> tuple[str, set[str], int]:
    data = path.read_bytes()
    if not data.startswith((b"Vocaloid Motion Data 0002", b"Vocaloid Motion Data file")):
        raise ValueError(f"Not a VMD motion: {path}")
    old = data.startswith(b"Vocaloid Motion Data file")
    model_size = 10 if old else 20
    model = data[30 : 30 + model_size].split(b"\0", 1)[0].decode("cp932", "replace")
    count = struct.unpack_from("<I", data, 30 + model_size)[0]
    offset = 34 + model_size
    if count > (len(data) - offset) // 111:
        raise ValueError(f"Truncated VMD bone frames: {path}")
    names = {
        data[offset + i * 111 : offset + i * 111 + 15]
        .split(b"\0", 1)[0]
        .decode("cp932", "replace")
        for i in range(count)
    }
    return model, names, count


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("motion", type=Path, help="VMD motion to inspect")
    ap.add_argument("models", nargs="+", type=Path, help="PMX target model(s)")
    ap.add_argument("--reader-root", type=Path, help="optional pymeshio install directory")
    args = ap.parse_args()
    if args.reader_root:
        sys.path.insert(0, str(args.reader_root))
    from pymeshio.pmx import reader

    model_name, tracks, frames = vmd_tracks(args.motion)
    report = {
        "vmdModel": model_name,
        "vmdBoneFrames": frames,
        "vmdTracks": len(tracks),
        "models": [],
        "warning": "Name coverage does not prove rest-pose, IK, append, physics or camera fidelity.",
    }
    normalize = lambda name: unicodedata.normalize("NFKC", name)
    for path in args.models:
        model = reader.read_from_file(str(path))
        names = {normalize(bone.name) for bone in model.bones}
        missing = sorted(name for name in tracks if normalize(name) not in names)
        report["models"].append(
            {
                "path": str(path),
                "name": model.name,
                "bones": len(model.bones),
                "vertices": len(model.vertices),
                "ikControllers": sum(bone.ik is not None for bone in model.bones),
                "matchedTracks": len(tracks) - len(missing),
                "missingTracks": missing,
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
