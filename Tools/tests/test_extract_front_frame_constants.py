import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "extract_front_frame_constants", Path(__file__).parents[1] / "extract_front_frame_constants.py")
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


def variant(set0=(22,), size=16, binding=0, member_size=16):
    return {
        "cbuffers": {"UnityPerMaterial": {
            "binding": binding, "space": 1, "size": size,
            "members": [{"offset": 0, "size": member_size, "name": "_BaseColor", "type": "float4"}]}},
        "resources": [{"binding": 1, "space": 1, "reg": "t", "kind": "Texture2D", "name": "_BaseMap"}]
        + [{"binding": b, "space": 0, "reg": "t", "kind": "Texture2D", "name": "_Global" + str(b)} for b in set0],
    }


class VariantSelectionTests(unittest.TestCase):
    def select(self, files, hint=None):
        return extract.pick_variant(files, hint, {"binding": 0, "set": 1, "size": 16},
                                    [(0, 16)], [1], [22])

    def test_body_hint_is_skin_from_texture_binding_evidence(self):
        self.assertEqual(extract.MAIN_EVENTS[786], ("body", "characternpr_skin"))

    def test_wrong_hint_cannot_exclude_better_global_match(self):
        files = {("cloth", "wrong.hlsl"): variant(set0=(22, 45)),
                 ("skin", "right.hlsl"): variant()}
        result = self.select(files, ["cloth"])
        self.assertEqual(result[0][1:3], ("skin", "right.hlsl"))
        self.assertEqual(len(result), 2)

    def test_hint_breaks_tie_without_removing_ambiguity_candidates(self):
        files = {("aaa", "a.hlsl"): variant(), ("skin", "b.hlsl"): variant()}
        result = self.select(files, ["skin"])
        self.assertEqual(result[0][1], "skin")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], result[1][0])

    def test_no_hint_preserves_deterministic_order(self):
        result = self.select({("z", "z.hlsl"): variant(), ("a", "a.hlsl"): variant()})
        self.assertEqual([r[1] for r in result], ["a", "z"])

    def test_unknown_hint_does_not_hide_valid_matches(self):
        self.assertEqual(len(self.select({("skin", "b.hlsl"): variant()}, ["missing"])), 1)

    def test_size_and_binding_mismatch_remain_rejected(self):
        files = {("skin", "size.hlsl"): variant(size=32),
                 ("skin", "binding.hlsl"): variant(binding=1)}
        self.assertEqual(self.select(files), [])

    def test_member_layout_match_outranks_hint(self):
        files = {("cloth", "wrong.hlsl"): variant(member_size=4),
                 ("skin", "right.hlsl"): variant()}
        self.assertEqual(self.select(files, ["cloth"])[0][1], "skin")

    def test_texture_binding_score_ignores_buffers_and_samplers(self):
        info = variant()
        info["resources"] += [
            {"binding": 47, "space": 0, "reg": "t", "name": "_Buffer", "kind": "StructuredBuffer"},
            {"binding": 3, "space": 1, "reg": "s", "name": "_Sampler", "kind": "SamplerState"}]
        for resource in info["resources"]:
            resource.setdefault("kind", "Texture2D")
        result = extract.score_variant(info, {"binding": 0, "set": 1, "size": 16}, [(0, 16)], [1], [22])
        self.assertEqual(result["score"], 5)

    def test_reviewed_texture_semantics_resolve_same_layout(self):
        wrong, right = variant(), variant()
        wrong["resources"][0]["name"] = "_SDFMask"
        result = extract.pick_variant({("skin", "a.hlsl"): wrong, ("skin", "b.hlsl"): right},
            ["skin"], {"binding": 0, "set": 1, "size": 16}, [(0, 16)], [1], [22],
            expected_texture_names={1: "_BaseMap"})
        self.assertEqual([r[2] for r in result], ["b.hlsl"])


if __name__ == "__main__":
    unittest.main()
