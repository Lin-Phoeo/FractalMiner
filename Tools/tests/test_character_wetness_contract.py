"""Source boundary guards; GPU and user previews are separate gates."""

import re
import runpy
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "Assets/EndfieldShaderPack/EndfieldOfficialWetness.hlsl"
SOURCE = (
    ROOT.parent
    / "EndfieldUnpacker/ShiyumeAssets/sm_153/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr/characternpr/Sub0_Pass0_Fragment_b471.hlsl"
)


def test_wet_formula_block_is_source_not_brightness_approximation():
    source = SOURCE.read_text(encoding="utf-8")
    block = source[
        source.index("    float3 _1828 =") : source.index("    float3 _1964 =")
    ]
    expected = (
        block.replace("sampler_LinearClamp", "sampler_BumpMap")
        .replace("_GlobalMipBias", "_EndfieldCapturedGlobalMipBias")
        .replace("_Time.x", "EFWetTime()")
    )
    helper = HELPER.read_text(encoding="utf-8")
    actual = helper.split("// SOURCE_BLOCK_BEGIN\n", 1)[1].split(
        "// SOURCE_BLOCK_END", 1
    )[0]
    assert re.sub(r"\s+", "", actual) == re.sub(r"\s+", "", expected)


def test_dry_default_and_rest_data_gate():
    shader = (ROOT / "Assets/EndfieldShaderPack/EndfieldCharacterLit.shader").read_text(
        encoding="utf-8"
    )
    assert "_EndfieldCharacterWetnessEnabled" in shader
    assert "restPosition.w > 0.5" in shader
    assert "_EndfieldWeatherTexturesReady > 0.5" in shader


def test_cloth02_wet_block_is_alpha_rename_of_reviewed_cloth01():
    first = SOURCE.read_text(encoding="utf-8")
    second = SOURCE.with_name("Sub0_Pass0_Fragment_b472.hlsl").read_text(
        encoding="utf-8"
    )
    first = first[first.index("    float3 _1828 =") : first.index("    float3 _1964 =")]
    second = second[
        second.index("    float3 _1842 =") : second.index("    float3 _1978 =")
    ]

    def normalize(block):
        names = {}

        def rename(match):
            return names.setdefault(match[0], f"v{len(names)}")

        return re.sub(r"\s+", "", re.sub(r"\b_\d+\b", rename, block))

    assert normalize(first) == normalize(second)


def test_no_scalar_weather_writes_in_motion_drivers():
    for name in ("EndfieldClipDriver", "EndfieldAclIkDriver"):
        code = (ROOT / f"Assets/EndfieldShaderPack/Editor/{name}.cs").read_text(
            encoding="utf-8"
        )
        assert "new Vector4(wetness > 0f ? 1f : 0f, wetness, 0f, 0f)" not in code
        assert "EndfieldCharacterWeather.Pack" in code


def test_preview_request_has_explicit_weather_scope_and_skin_refresh():
    code = (
        ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldWetnessStudio.cs"
    ).read_text(encoding="utf-8")
    assert "using (Weather.BeginRenderScope())" in code
    assert "forceMatrixRecalculationPerRender = true" in code


def test_mmd_initialization_restores_all_canonical_bones_before_calibration():
    code = (
        ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldWetnessStudio.cs"
    ).read_text(encoding="utf-8")
    assert code.index("RestoreCanonicalBindPose(Root);") < code.index(
        "InitialPose = MmdRetargetProfile.FromUnity(Root);"
    )


@pytest.mark.parametrize("fails", [False, True])
def test_offline_weather_entrypoint_reports_failure_not_success(monkeypatch, fails):
    calls = []

    def run(*args):
        calls.append(args)
        if fails:
            raise OSError("synthetic replay failure")

    module = types.ModuleType("capture_cloth_materials")
    monkeypatch.setattr(module, "run", run, raising=False)
    monkeypatch.setitem(sys.modules, "capture_cloth_materials", module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(ROOT / "Tools/capture_character_weather.py"), run_name="__main__"
        )
    assert error.value.code == int(fails)
    assert calls == [
        ({835: {"Rain": 44, "Streak": 41}}, {835: 22255}, {"Rain": 4, "Streak": 4}, 0)
    ]
