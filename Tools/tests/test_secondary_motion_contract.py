"""Ownership/integration guards; actual numerical tests run inside Unity."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "Assets/EndfieldShaderPack/Editor"


def test_reviewed_edge_endpoints_have_real_weights_not_identity_tip_fallback():
    data = json.loads((ROOT / "Assets/Typhoeus/_typhoea_model_data.json").read_text())
    names = {b["name"]: i for i, b in enumerate(data["bones"])}
    weighted = {
        mesh["bones"][i]
        for mesh in data["meshes"]
        for i, w in zip(mesh["boneWeightIndices"], mesh["boneWeightValues"], strict=True)
        if w > 0
    }
    edges = 0
    for prefix, end in [
        ("hair_R_base_a_", 6),
        ("hair_L_base_a_", 6),
        ("tail_M_stone_a_", 7),
        *[(f"skirt_base_{part}_", 3) for part in ("R_c", "R_b", "R_a", "M_a", "L_c", "L_b", "L_a")],
    ]:
        for i in range(1, end):
            parent = names[f"{prefix}{i:02}_jnt"]
            child = names[f"{prefix}{i+1:02}_jnt"]
            assert data["bones"][child]["parent"] == parent
            assert parent in weighted and child in weighted
            edges += 1
        assert names[f"{prefix}{end+1:02}_jnt"] not in weighted
    assert edges == 30


def test_solver_owns_only_secondary_rotations_and_has_no_wall_clock_driver():
    code = (EDITOR / "EndfieldSecondaryMotion.cs").read_text(encoding="utf-8")
    assert "UniVRM v0.99.4" in code and "MIT License" in code
    assert "1.0/120.0" in code
    assert "Time.deltaTime" not in code and "LateUpdate" not in code
    assert "localPosition=" not in code and "localScale=" not in code
    assert 'Chain("hair_R_base_a_",6,true)' in code
    assert 'Chain("skirt_base_"+side+"_",3,false)' in code
    assert 'Chain("tail_M_stone_a_",7,false)' in code
    assert "RestorePose();applyAnimatedPose" in code
    assert "wanted<tick" in code and "tick=-1" in code


def test_studio_export_and_preview_share_physics_and_invalidate_changed_inputs():
    code = (EDITOR / "EndfieldMmdStudio.cs").read_text(encoding="utf-8")
    export = code[code.index("IEnumerator RunRender(") :]
    assert "ApplyAt(t); // exactly the preview" in export
    assert "player.ApplyFrame(" not in export
    assert "secondaryMotion?.ResetTimeline();" in export
    assert "secondaryMotion.Evaluate(t, ApplyAnimatedPose, secondaryMotionEnabled)" in code
    assert "!inputs.Equals(lastPhysicsInputs)" in code
    assert code.index("secondaryMotion?.Dispose();") < code.index("renderSession?.Dispose();")


def test_unity_validation_exercises_real_studio_and_weighted_meshes():
    code = (EDITOR / "EndfieldSecondaryMotionValidation.cs").read_text(encoding="utf-8")
    for evidence in (
        "smr.BakeMesh(mesh)",
        "direct seek and incremental playback",
        "backward scrub",
        'Call("RunRender",1,2f)',
        'Call("LoadMotion",',
        "zero length collision input rejected",
        "dispose restores owned joint",
    ):
        assert evidence in code
