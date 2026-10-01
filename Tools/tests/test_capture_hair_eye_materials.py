"""Actual Hair/Eye binding and source-sampling guards, not screenshot fitting."""

import importlib
import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_cloth_materials as core
import capture_hair_eye_materials as plan
from test_capture_cloth_materials import Fixture, sampler

ROOT = Path(__file__).resolve().parents[2] / "Assets/EndfieldShaderPack"


def test_export_plan_uses_actual_program_roles():
    module = importlib.import_module("capture_hair_eye_materials")
    assert module.ROLES == {
        875: {"HN": 1, "SpecRamp": 2, "P": 3, "Line": 4, "DiffRamp": 5, "Base": 6},
        776: {"Matcap": 1, "DiffRamp": 2, "Base": 3},
    }
    assert module.PROGRAMS == {875: 22257, 776: 22259}
    assert module.SAMPLERS == {
        "HN": 4,
        "SpecRamp": 6,
        "P": 4,
        "Line": 4,
        "DiffRamp": 6,
        "Base": 4,
        "Matcap": 6,
    }


def test_hair_ramps_use_actual_clamp_not_candidate_mirror():
    helper = (ROOT / "EndfieldOfficialHair.hlsl").read_text("utf-8-sig")
    assert "sampler_EFHair_LinearMirror" not in helper
    assert "SAMPLE_TEXTURE2D_LOD(_DiffRampMap, sampler_Endfield_LinearClamp," in helper
    assert "SAMPLE_TEXTURE2D_LOD(_SpecRampMap, sampler_Endfield_LinearClamp," in helper
    # Actual Line is implicit Sample, not SampleBias. It keeps its own ST.
    assert "SAMPLE_TEXTURE2D(_LineMap, sampler_Endfield_LinearRepeat," in helper
    assert "TRANSFORM_TEX(uv, _LineMap)" in helper


def test_eye_uses_captured_vs_uv_and_bias_sampler():
    helper = (ROOT / "EndfieldOfficialEye.hlsl").read_text("utf-8-sig")
    shader = (ROOT / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
    assert "EndfieldShadeOfficialEye(sourceUV," in shader
    assert "_BaseMap_ST" not in helper
    assert (
        "_BaseMap, sampler_Endfield_LinearRepeat, baseUV, _EndfieldCapturedGlobalMipBias"
        in helper
    )
    assert (
        "_MatcapTex, sampler_Endfield_LinearClamp, matcapUV, _EndfieldCapturedGlobalMipBias"
        in helper
    )
    assert "sampler_Endfield_LinearRepeat, float2(rampU" not in helper
    assert "mip bias is zero" not in helper


class HairEyeFixture(Fixture):
    """API/IO fixture, never substituted for the real native GPU replay."""

    def __init__(self, fail=""):
        super().__init__(fail)
        self.event = 875

    @staticmethod
    def format_for(role):
        return (
            "BC7_SRGB"
            if role in ("Matcap", "Base")
            else "R8G8B8A8_UNORM"
            if role.endswith("Ramp")
            else "BC7_UNORM"
        )

    def GetTextures(self):
        return [
            NS(
                resourceId=role,
                width=4,
                height=4,
                depth=1,
                arraysize=1,
                mips=2,
                format=NS(Name=lambda role=role: self.format_for(role)),
            )
            for role in plan.SAMPLERS
        ]

    def GetReadOnlyResources(self, stage):
        values = super().GetReadOnlyResources(stage)
        for value in values:
            role = value.descriptor.resource
            value.descriptor.format = NS(Name=lambda role=role: self.format_for(role))
        return values

    def GetTextureData(self, resource, sub):
        size = core.level_bytes(
            max(1, 4 >> sub.mip), max(1, 4 >> sub.mip), self.format_for(resource)
        )
        return b"x" * (size - (1 if self.fail == "truncated" else 0))


def test_eye_normalizes_projected_light_at_actual_ramp_consumer():
    helper = (ROOT / "EndfieldOfficialEye.hlsl").read_text("utf-8-sig")
    assert "dot(shadingNormalWS, EFEyeNormalize(rampLightWS))" in helper


def test_actual_plan_collects_views_samplers_and_bytes():
    f = HairEyeFixture()
    with (
        tempfile.TemporaryDirectory() as folder,
        patch.object(core, "ROLES", plan.ROLES),
        patch.object(core, "PROGRAMS", plan.PROGRAMS),
        patch.object(core, "sampler_record", side_effect=lambda s: sampler(s.number)),
    ):
        records = core.collect(
            f.rd, f, Path(folder), plan.ROLES, plan.PROGRAMS, plan.SAMPLERS
        )
        assert len(records) == 9
        for record in records:
            assert record["sampler"]["binding"] == plan.SAMPLERS[record["role"]]
            assert record["sample_cast"] == (
                "CompType.UNormSRGB"
                if record["role"] in ("Matcap", "Base")
                else "CompType.UNorm"
            )
            assert len(record["native_samples"]) == 10
            assert (Path(folder) / record["file"]).stat().st_size == record["bytes"]


@pytest.mark.parametrize("failure", ["", "shader", "shutdown", "truncated"])
def test_complete_requires_successful_replay_and_shutdown(failure):
    f = HairEyeFixture(failure)
    with tempfile.TemporaryDirectory() as folder:
        capture = Path(folder) / "fixture.rdc"
        capture.write_bytes(b"offline fixture")
        output = Path(folder) / "out"
        with (
            patch.dict(
                core.os.environ,
                ENDFIELD_CAPTURE_PATH=str(capture),
                ENDFIELD_CAPTURE_OUTPUT=str(output),
            ),
            patch.dict(sys.modules, renderdoc=f.rd),
            patch.object(
                core, "open_controller", return_value=(NS(Shutdown=lambda: None), f)
            ),
            patch.object(core, "ROLES", plan.ROLES),
            patch.object(core, "PROGRAMS", plan.PROGRAMS),
            patch.object(
                core, "sampler_record", side_effect=lambda s: sampler(s.number)
            ),
        ):
            if failure:
                with pytest.raises((ValueError, RuntimeError)):
                    plan.run()
                assert (output / "error.json").exists()
                assert not (output / "complete.json").exists()
            else:
                plan.run()
                assert (output / "complete.json").exists()
            assert f.closed


def test_renderdoc_main_forwards_plan_then_exits():
    with patch.object(core, "run") as run, pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(plan.__file__)), run_name="__main__")
    assert stopped.value.code is None
    run.assert_called_once_with(plan.ROLES, plan.PROGRAMS, plan.SAMPLERS)
