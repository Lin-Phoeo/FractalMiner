"""Identity-based graph gates; names must never be primary keys."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_bindings import (
    build_bindings,
    check_read_warnings,
    export_files,
)


def ptr(pid, file_id=0):
    return {"m_FileID": file_id, "m_PathID": pid}


def fixture():
    objects = []
    for pid, name, parent, children in (
        (1, "Root", 0, [2, 3, 4]),
        (2, "same", 1, []),
        (3, "same", 1, []),
        (4, "collider", 1, []),
    ):
        components = [ptr(pid)]
        if pid == 1:
            components.append(ptr(100))
        if pid == 4:
            components.append(ptr(101))
        objects.append(
            {
                "source": "CAB-test",
                "path_id": pid + 10,
                "type": "GameObject",
                "data": {
                    "m_Name": name,
                    "m_Component": [{"component": item} for item in components],
                    "m_IsActive": True,
                },
            }
        )
        objects.append(
            {
                "source": "CAB-test",
                "path_id": pid,
                "type": "Transform",
                "data": {
                    "m_GameObject": ptr(pid + 10),
                    "m_Father": ptr(parent),
                    "m_Children": [ptr(child) for child in children],
                    "m_LocalPosition": {"x": 0.1, "y": 0.0, "z": 0.0},
                    "m_LocalRotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                    "m_LocalScale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            }
        )
    settings = {
        "rootBones": [ptr(2), ptr(3)],
        "ignoreFromRootBones": [],
        "colliderCollisionConstraint": {"colliderList": [ptr(101)]},
    }
    for pid, go, data in (
        (100, 11, {"serializeData": settings}),
        (
            101,
            14,
            {
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
                "size": {"x": 0.1, "y": 0.2, "z": 0.3},
                "direction": 0,
                "reverseDirection": 0,
                "radiusSeparation": 1,
                "alignedOnCenter": 0,
            },
        ),
    ):
        objects.append(
            {
                "source": "CAB-test",
                "path_id": pid,
                "type": "MonoBehaviour",
                "data": {
                    "m_GameObject": ptr(go),
                    "m_Enabled": 1,
                    "m_Script": ptr(-900, 1),
                    **copy.deepcopy(data),
                },
            }
        )
    group = {
        "boneClothName": "MBC_Typhoea_Test",
        "boneClothData": copy.deepcopy(settings),
        "rootBoneList": ["same", "same"],
        "ignoredFromrootBoneList": [],
        "colliderParentBoneList": ["collider"],
    }

    def externalize(value):
        if isinstance(value, dict):
            if "m_FileID" in value:
                value["m_FileID"] = 2 if value["m_PathID"] else 0
            else:
                for item in value.values():
                    externalize(item)
        elif isinstance(value, list):
            for item in value:
                externalize(item)

    externalize(group["boneClothData"])
    return objects, [group]


def test_duplicate_names_and_exact_64_bit_identity():
    objects, groups = fixture()
    result = build_bindings(objects, groups)
    assert result["transform_count"] == 4
    assert result["duplicate_names"] == {"same": ["CAB-test:2", "CAB-test:3"]}
    assert [item["id"] for item in result["groups"][0]["roots"]] == [
        "CAB-test:2",
        "CAB-test:3",
    ]
    assert result["colliders"][0]["class_resolved"] is False
    assert result["runtime_restored"] is False
    objects[-1]["path_id"] = 9007199254740993
    objects[6]["data"]["m_Component"][1]["component"] = ptr(9007199254740993)
    objects[-2]["data"]["serializeData"]["colliderCollisionConstraint"][
        "colliderList"
    ] = [ptr(9007199254740993)]
    groups[0]["boneClothData"]["colliderCollisionConstraint"]["colliderList"] = [
        ptr(9007199254740993, 2)
    ]
    assert build_bindings(objects, groups)["colliders"][0]["id"].endswith(
        ":9007199254740993"
    )


def test_original_size_only_collider_preserves_unresolved_semantics():
    objects, groups = fixture()
    data = objects[-1]["data"]
    for key in ("direction", "reverseDirection", "radiusSeparation", "alignedOnCenter"):
        del data[key]
    data["size"] = {"x": 0.078, "y": 0.0, "z": 0.0}
    collider = build_bindings(objects, groups)["colliders"][0]
    assert collider["shape_fingerprint"] == "size_only_fields"
    assert collider["raw_component"]["size"]["x"] == 0.078
    assert collider["class_resolved"] is False


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_id",
        "float_id",
        "dangling",
        "external",
        "reciprocal",
        "duplicate_child",
        "owner",
        "cycle",
        "quaternion",
        "scale",
        "nonfinite",
        "inactive",
        "disabled",
        "unknown_collider",
        "root_name",
        "collider_name",
        "ignore",
        "missing_cloth",
        "ambiguous_cloth",
        "empty",
    ],
)
def test_corrupt_bindings_fail_closed(case):
    objects, groups = fixture()
    if case == "duplicate_id":
        objects.append(copy.deepcopy(objects[0]))
    elif case == "float_id":
        objects[3]["data"]["m_Father"]["m_PathID"] = 1.0
    elif case == "dangling":
        objects[3]["data"]["m_Father"] = ptr(99)
    elif case == "external":
        objects[3]["data"]["m_Father"] = ptr(1, 1)
    elif case == "reciprocal":
        objects[1]["data"]["m_Children"] = [ptr(3), ptr(4)]
    elif case == "duplicate_child":
        objects[1]["data"]["m_Children"].append(ptr(2))
    elif case == "owner":
        objects[3]["data"]["m_GameObject"] = ptr(13)
    elif case == "cycle":
        objects[1]["data"]["m_Father"] = ptr(2)
        objects[3]["data"]["m_Children"] = [ptr(1)]
    elif case == "quaternion":
        objects[1]["data"]["m_LocalRotation"]["w"] = 0.0
    elif case == "scale":
        objects[1]["data"]["m_LocalScale"]["x"] = 0.0
    elif case == "nonfinite":
        objects[1]["data"]["m_LocalPosition"]["x"] = float("nan")
    elif case == "inactive":
        objects[0]["data"]["m_IsActive"] = False
    elif case == "disabled":
        objects[-1]["data"]["m_Enabled"] = 0
    elif case == "unknown_collider":
        del objects[-1]["data"]["size"]
    elif case == "root_name":
        groups[0]["rootBoneList"][1] = "wrong"
    elif case == "collider_name":
        groups[0]["colliderParentBoneList"] = ["Root"]
    elif case == "ignore":
        groups[0]["boneClothData"]["ignoreFromRootBones"] = [ptr(999, 2)]
    elif case == "missing_cloth":
        objects.pop(-2)
    elif case == "ambiguous_cloth":
        obj = copy.deepcopy(objects[-2])
        obj["path_id"] = 102
        objects.append(obj)
        objects[0]["data"]["m_Component"].append({"component": ptr(102)})
    elif case == "empty":
        groups.clear()
    with pytest.raises(ValueError):
        build_bindings(objects, groups)


def test_export_rejects_overwrite_and_unsafe_metadata_paths(tmp_path: Path):
    manifest = tmp_path / "scene_manifest.json"
    cloth = tmp_path / "cloth.json"
    output = tmp_path / "out.json"
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_files(manifest, cloth, output)
    assert output.read_text() == "keep"
    manifest.write_text(
        json.dumps(
            {
                "MetadataExports": [
                    {
                        "File": "../escape.txt",
                        "Error": None,
                        "Asset": {"Source": "s", "PathId": 1, "Type": "Transform"},
                    }
                ]
            }
        )
    )
    cloth.write_text(json.dumps({"groups": []}))
    with pytest.raises(ValueError, match="outside"):
        export_files(manifest, cloth, tmp_path / "fresh.json")


def test_reader_warnings_cannot_certify_critical_objects():
    objects, groups = fixture()
    result = build_bindings(objects, groups)
    for pid in (1, 11, 100, 101, 999):
        with pytest.raises(ValueError, match="reader warning"):
            check_read_warnings(
                result,
                [{"Source": "CAB-test", "PathId": pid, "Messages": ["read mismatch"]}],
            )
    objects.append(
        {"source": "CAB-test", "path_id": 200, "type": "MonoBehaviour", "data": {}}
    )
    result = build_bindings(objects, groups)
    warnings = [{"Source": "CAB-test", "PathId": 200, "Messages": ["read mismatch"]}]
    check_read_warnings(result, warnings)
    assert result["unvalidated_metadata_warnings"] == warnings
    assert result["critical_metadata_reader_warnings"] == 0


def test_full_file_integration_and_hashes(tmp_path: Path):
    objects, groups = fixture()

    def dump_field(name, value, depth):
        tab = "\t" * depth
        if isinstance(value, dict):
            return [f"{tab}Structure {name}"] + [
                line
                for key, item in value.items()
                for line in dump_field(key, item, depth + 1)
            ]
        if isinstance(value, list):
            lines = [
                f"{tab}vector {name}",
                f"{tab}\tArray Array",
                f"{tab}\tint size = {len(value)}",
            ]
            for index, item in enumerate(value):
                lines += [f"{tab}\t\t[{index}]"] + dump_field("data", item, depth + 2)
            return lines
        kind = (
            "bool"
            if type(value) is bool
            else "SInt64"
            if type(value) is int
            else "float"
            if type(value) is float
            else "string"
        )
        raw = str(value) if kind != "string" else json.dumps(value)
        return [f"{tab}{kind} {name} = {raw}"]

    records = []
    for index, obj in enumerate(objects):
        filename = f"{index}.txt"
        (tmp_path / filename).write_text(
            "\n".join(dump_field("Base", obj["data"], 0)), encoding="utf-8"
        )
        records.append(
            {
                "File": filename,
                "Asset": {
                    "Source": obj["source"],
                    "PathId": obj["path_id"],
                    "Type": obj["type"],
                },
            }
        )
    manifest = tmp_path / "scene_manifest.json"
    cloth = tmp_path / "cloth.json"
    output = tmp_path / "out.json"
    manifest.write_text(json.dumps({"MetadataExports": records}), encoding="utf-8")
    cloth.write_text(json.dumps({"groups": groups}), encoding="utf-8")
    (tmp_path / "metadata-read-warnings.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected 11"):
        export_files(manifest, cloth, output)
    export_files(manifest, cloth, output, expected_groups=1)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["source_sha256"]) == len(objects) + 3
    assert result["transform_count"] == 4
    assert result["critical_metadata_reader_warnings"] == 0
    assert result["raw_objects"][0]["raw_scalars"]
