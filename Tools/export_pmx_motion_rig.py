"""Export a PMX *motion-source skeleton* for local A/B tests, without mesh data.

Requires pymeshio (https://github.com/ousttrue/pymeshio). The JSON derives from
the user's PMX: keep it local and respect the model author's redistribution terms.
"""

import argparse
import json
from pathlib import Path
import sys
import unicodedata


def vector(value):
    return [float(value.x), float(value.y), float(value.z)]


def export_rig(model):
    count = len(model.bones)
    if not 1 <= count <= 10000:
        raise ValueError(f"invalid bone count: {count}")

    def check(index, field):
        if index < -1 or index >= count:
            raise ValueError(f"invalid {field} index: {index}")
        return index

    bones = []
    names = set()
    for index, source in enumerate(model.bones):
        name = unicodedata.normalize("NFKC", source.name)
        if not name or name in names:
            raise ValueError(f"missing or duplicate bone name: {name!r}")
        names.add(name)
        parent = check(source.parent_index, "parent")
        if parent == index:
            raise ValueError(f"bone {name!r} is its own parent")
        flags = source.flag
        grant_rotation = bool(flags & 0x0100)
        grant_position = bool(flags & 0x0200)
        grant = check(source.effect_index, "grant") if grant_rotation or grant_position else -1
        if grant == index:
            raise ValueError(f"bone {name!r} grants to itself")
        ik = source.ik
        links = []
        if ik is not None:
            check(ik.target_index, "IK effector")
            for link in ik.link:
                links.append({
                    "bone": check(link.bone_index, "IK link"),
                    "limited": bool(link.limit_angle),
                    "minimum": vector(link.limit_min),
                    "maximum": vector(link.limit_max),
                })
        bones.append({
            "name": name,
            "rest": vector(source.position),
            "parent": parent,
            "layer": int(source.layer),
            "grant": grant,
            "grantWeight": float(source.effect_factor) if grant >= 0 else 0.0,
            "grantRotation": grant_rotation,
            "grantPosition": grant_position,
            "grantLocal": False,
            "fixedAxis": bool(flags & 0x0400),
            "axis": vector(source.fixed_axis),
            "effector": ik.target_index if ik is not None else -1,
            "iterations": int(ik.loop) if ik is not None else 0,
            "angleLimit": float(ik.limit_radian) if ik is not None else 0.0,
            "links": links,
        })
    return {"name": model.name, "bones": bones}


def validate_paths(model: Path, output: Path, force: bool):
    if not model.is_file() or model.suffix.lower() != ".pmx" or model.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("PMX input is missing, invalid, or exceeds 256 MiB")
    if model.resolve() == output.resolve():
        raise ValueError("Input and output refer to the same file")
    if output.suffix.lower() != ".json":
        raise ValueError("Output must be a .json file")
    if output.exists() and not force:
        raise FileExistsError(f"Output exists; pass --force to replace: {output}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path, help="source PMX file")
    ap.add_argument("output", type=Path, help="local JSON output; do not redistribute")
    ap.add_argument("--reader-root", type=Path, help="optional pymeshio install directory")
    ap.add_argument("--force", action="store_true", help="replace an existing JSON output")
    args = ap.parse_args()
    validate_paths(args.model, args.output, args.force)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.reader_root:
        sys.path.insert(0, str(args.reader_root))
    from pymeshio.pmx import reader

    data = export_rig(reader.read_from_file(str(args.model)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    print(f"Exported {len(data['bones'])} motion bones to {args.output}")


if __name__ == "__main__":
    main()
