"""Lossless offline cloth settings audit; synthetic fixtures, no game assets."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_official_cloth_config as audit


def array(field, values, depth=1, value_type="string"):
    tab = "\t" * depth
    lines = [
        f"{tab}vector {field}",
        f"{tab}\tArray Array",
        f"{tab}\tint size = {len(values)}",
    ]
    for index, value in enumerate(values):
        lines += [f"{tab}\t\t[{index}]", f"{tab}\t\t{value_type} data = {value}"]
    return "\n".join(lines)


CONFIG = """ClothSerializeData CONFIG
	int clothType = 1
	vector rootBones
		Array Array
		int size = 1
			[0]
			PPtr<$Transform> data
				int m_FileID = FILE
				SInt64 m_PathID = -8863479361307848913
	float gravity = 0
	CurveSerializeData damping
		float value = 0.08
		UInt8 useCurve = 1
		AnimationCurve curve
			vector m_Curve
				Array Array
				int size = 1
					[0]
					Keyframe data
						float time = 0
						float value = 1.4764835E-07
						float inSlope = -0.5
						float outSlope = 0
						int weightedMode = 0
"""
SELECTION = """SelectionData selectionData
	float3 positions
		Array Array
		int size = 1
			[0]
			float3 data
				float x = 0
				float y = 1
				float z = 0
	VertexAttribute attributes
		Array Array
		int size = 1
			[0]
			VertexAttribute data
				UInt8 Value = 1
	float maxConnectionDistance = 0.2
	UInt8 userEdit = 0
"""


def indent(text, depth):
    return "\n".join("\t" * depth + line for line in text.rstrip().splitlines())


def fixtures():
    group = 'string boneClothName = "MBC_Typhoea_Tail"\n'
    group += CONFIG.replace("CONFIG", "boneClothData").replace("FILE", "2")
    group += SELECTION
    group += array("rootBoneList", ['"tail_M_stone_a_01_jnt"'], depth=0) + "\n"
    group += array("ignoredFromrootBoneList", [], depth=0) + "\n"
    group += array("skinningBoneList", [], depth=0) + "\n"
    group += array("colliderParentBoneList", [], depth=0)
    avatar = (
        "MonoBehaviour Base\n\tBoneClothItem boneClothItems\n\t\tArray Array\n\t\tint size = 1\n\t\t\t[0]\n\t\t\tBoneClothItem data\n"
        + indent(group, 4)
    )
    prefab = "MonoBehaviour Base\n\tUInt8 m_Enabled = 1\n"
    prefab += (
        indent(CONFIG.replace("CONFIG", "serializeData").replace("FILE", "0"), 1) + "\n"
    )
    prefab += "\tClothSerializeData2 serializeData2\n" + indent(SELECTION, 2)
    return avatar, {"component.txt": prefab}


class DumpParserTests(unittest.TestCase):
    def test_preserves_large_integer_curve_and_original_lexeme(self):
        avatar, _ = fixtures()
        parsed = audit.parse_dump(avatar)
        group = parsed.data["boneClothItems"][0]
        self.assertEqual(
            group["boneClothData"]["rootBones"][0]["m_PathID"], -8863479361307848913
        )
        self.assertEqual(group["boneClothData"]["gravity"], 0)
        self.assertEqual(group["ignoredFromrootBoneList"], [])
        self.assertIn("1.4764835E-07", [entry["raw"] for entry in parsed.scalars])
        self.assertEqual(
            json.loads(json.dumps(group))["boneClothData"]["rootBones"][0]["m_PathID"],
            -8863479361307848913,
        )

    def test_scalar_types(self):
        result = audit.parse_dump(
            'Object Base\n\tbool active = True\n\tstring label = "测试"\n\tunsigned int bits = 4294967295\n\tdouble value = -2.5'
        )
        self.assertEqual(
            result.data,
            {"active": True, "label": "测试", "bits": 4294967295, "value": -2.5},
        )

    def test_prebuild_integer_buffers_are_not_discarded(self):
        parsed = audit.parse_dump(
            "Object Base\n\tUInt16 index = 65535\n\tSInt16 signed = -32768"
        )
        self.assertEqual(parsed.data, {"index": 65535, "signed": -32768})
        for kind, value in (("UInt16", "65536"), ("SInt16", "32768")):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                audit.parse_dump(f"Object Base\n\t{kind} index = {value}")

    def test_rejects_malformed_or_ambiguous_input(self):
        cases = [
            "",
            "Object Base\nOther Base",
            "Object Base\n\t\tint x = 1",
            "Object Base\n int x = 1",
            "Object Base\n\tint x = 1\n\tint x = 2",
            "Object Base\n\tfloat x = NaN",
            "Object Base\n\tfloat x = Infinity",
            "Object Base\n\tUInt8 x = 256",
            "Object Base\n\tSInt64 x = 9223372036854775808",
            "Object Base\n\tbool x = maybe",
            "Object Base\n\tunknown x = 3",
            'Object Base\n\tstring x = "unterminated',
            "Object Base\n\tint x = 1\n\t\tint y = 2",
            "Object Base\n\t[0]",
            "Object Base\n\tinvalid",
            "Object Base\n"
            + array("items", ["3"], value_type="int").replace("size = 1", "size = 2"),
            "Object Base\n"
            + array("items", ["3"], value_type="int").replace("[0]", "[1]"),
            "Object Base\n"
            + array("items", ["3"], value_type="int").replace(
                "[0]", "[0]\n\t\t\t\tint illegal = 1"
            ),
            "Object Base\n"
            + array("items", ["3"], value_type="int").replace(
                "int data = 3", "int other = 3"
            ),
            "Object Base\n\tvector items\n\t\tArray Array",
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                audit.parse_dump(text)


class ManifestTests(unittest.TestCase):
    def test_equal_numeric_values_cannot_hide_a_changed_scalar_type(self):
        avatar, prefabs = fixtures()
        with self.assertRaises(ValueError):
            audit.build_manifest(
                avatar.replace("float gravity = 0", "int gravity = 0"),
                prefabs,
                expected_groups=1,
            )

    def test_reference_file_ids_must_be_integers_not_equal_floats(self):
        avatar, prefabs = fixtures()
        with self.assertRaises(ValueError):
            audit.build_manifest(
                avatar.replace("int m_FileID = 2", "float m_FileID = 2"),
                prefabs,
                expected_groups=1,
            )

    def test_full_settings_and_selection_cross_check(self):
        avatar, prefabs = fixtures()
        manifest = audit.build_manifest(avatar, prefabs, expected_groups=1)
        self.assertEqual(len(manifest["groups"]), 1)
        self.assertEqual(manifest["verification"][0]["prefab"], "component.txt")
        self.assertTrue(manifest["verification"][0]["parameters_equal"])
        self.assertTrue(manifest["verification"][0]["selection_equal"])
        self.assertEqual(manifest["selection_positions_total"], 1)
        self.assertEqual(
            manifest["prefab_components"]["component.txt"]["serializeData2"][
                "selectionData"
            ]["positions"],
            [{"x": 0, "y": 1, "z": 0}],
        )
        self.assertFalse(manifest["runtime_restored"])

    def test_fails_closed_on_missing_or_wrong_runtime_settings(self):
        avatar, prefabs = fixtures()
        cases = [
            (avatar, {}, 1),
            (avatar, prefabs, 11),
            (avatar.replace("clothType = 1", "clothType = 0"), prefabs, 1),
            (avatar.replace("gravity = 0", "gravity = 2"), prefabs, 1),
            (avatar.replace("float inSlope = -0.5", "float inSlope = 0"), prefabs, 1),
            (
                avatar,
                {
                    "component.txt": prefabs["component.txt"].replace(
                        "m_Enabled = 1", "m_Enabled = 0"
                    )
                },
                1,
            ),
            (avatar, {**prefabs, "duplicate.txt": prefabs["component.txt"]}, 1),
            (
                avatar.replace("-8863479361307848913", "-8863479361307848912"),
                prefabs,
                1,
            ),
            (avatar.replace("int m_FileID = 2", "int m_FileID = 7"), prefabs, 1),
            (
                avatar.replace(
                    "VertexAttribute attributes\n\t\t\t\t\t\tArray Array\n\t\t\t\t\t\tint size = 1",
                    "VertexAttribute attributes\n\t\t\t\t\t\tArray Array\n\t\t\t\t\t\tint size = 0",
                ),
                prefabs,
                1,
            ),
            (avatar.replace("float y = 1", "float y = 2"), prefabs, 1),
            (avatar.replace('"MBC_Typhoea_Tail"', '"Other"'), prefabs, 1),
        ]
        for source, candidates, expected in cases:
            with (
                self.subTest(source=source[-100:], candidates=list(candidates)),
                self.assertRaises(ValueError),
            ):
                audit.build_manifest(source, candidates, expected_groups=expected)

    def test_cli_writes_new_file_and_never_overwrites(self):
        avatar, prefabs = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "avatar.txt"
            source.write_text(avatar, encoding="utf-8")
            component_dir = folder / "prefab"
            component_dir.mkdir()
            for name, text in prefabs.items():
                (component_dir / name).write_text(text, encoding="utf-8")
            output = folder / "settings.json"
            audit.export_files(source, component_dir, output, expected_groups=1)
            original = output.read_bytes()
            self.assertEqual(
                json.loads(original)["source"]["avatar"]["sha256"],
                audit.sha256_bytes(source.read_bytes()),
            )
            with self.assertRaises(FileExistsError):
                audit.export_files(source, component_dir, output, expected_groups=1)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
