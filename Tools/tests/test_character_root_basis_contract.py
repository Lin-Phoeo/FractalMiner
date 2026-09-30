"""Wiring guardrails; actual transform/formula checks run separately in Unity."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / 'Assets/EndfieldShaderPack'


def test_all_root_dependent_families_use_the_shared_source_root_input():
    for family in ('Skin', 'Hair', 'Eye'):
        text = (ROOT / f'EndfieldOfficial{family}.hlsl').read_text('utf-8')
        assert 'EndfieldCharacterRootToWorld()' in text, family
        assert 'GetObjectToWorldMatrix()' not in text, family
        assert 'unity_ObjectToWorld' not in text, family


def test_shared_root_helper_is_included_before_family_helpers():
    shader = (ROOT / 'EndfieldCharacterLit.shader').read_text('utf-8')
    assert shader.index('#include "EndfieldCharacterBasis.hlsl"') < shader.index('#include "EndfieldOfficialHair.hlsl"')


def test_eye_projected_light_preserves_source_length_after_removing_y():
    text = (ROOT / 'EndfieldOfficialEye.hlsl').read_text('utf-8')
    assert re.search(r'float3 rampLightWS\s*=\s*mul\(objectToWorld, objectLight\);', text)


def test_eye_cannot_emit_generic_outline_even_with_stale_enabled_material():
    shader = (ROOT / 'EndfieldCharacterLit.shader').read_text('utf-8')
    outline = shader[shader.index('Name "Outline"'):]
    assert 'clip(2.5 - _MaterialFamily);' in outline


def test_mmd_render_smoke_updates_root_inputs_after_foot_correction():
    text = (ROOT / 'Editor/EndfieldVmdBatchRender.cs').read_text('utf-8')
    smoke = text[text.index('public static void RunSmokeValidation()'):text.index('static Vector4 SkinnedViewportBounds')]
    assert smoke.index('KeepFeetAboveBindFloor') < smoke.index('EndfieldSkinBasisDriver.ApplyForTyphoeus(root)') < smoke.index('SaveFrame(camera')


def test_input_diagnostic_includes_hair_and_iris_and_eye_parallax_gate():
    text = (ROOT / 'Editor/EndfieldSkinInputDiagnostics.cs').read_text('utf-8')
    assert 'material.GetFloat("_MaterialFamily") >= 1.5f) continue' not in text
    assert 'material.GetFloat("_UseParallax") < .5f || family > 2.5f' in text
