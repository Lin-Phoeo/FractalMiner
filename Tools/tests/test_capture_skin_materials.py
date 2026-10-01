"""Skin descriptor/UV/sampler contracts, not official screenshot fitting."""

import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_cloth_materials as core
import capture_skin_materials as skin
from test_capture_cloth_materials import Fixture, sampler


def test_actual_variant_plan_and_sampler_roles():
    assert skin.PROGRAMS == {786: 22250, 860: 37671}
    assert skin.ROLES[786] == {"ShadowLUT": 1, "DiffRamp": 2, "Normal": 3, "Base": 4}
    assert skin.ROLES[860] == {
        "ShadowLUT": 1,
        "SDFMask": 2,
        "SDF": 3,
        "Highlight": 4,
        "Emotion": 5,
        "DiffRamp": 6,
        "Normal": 7,
        "Base": 8,
    }
    assert skin.SAMPLERS == {
        "ShadowLUT": 6,
        "DiffRamp": 6,
        "Normal": 4,
        "Base": 4,
        "SDFMask": 6,
        "SDF": 6,
        "Highlight": 4,
        "Emotion": 4,
    }


def test_normal_small_mips_preserved_without_conversion():
    assert core.level_bytes(2, 1, "BC5_UNORM") == 16


def test_skin_source_does_not_assume_zero_bias_or_repeat_lut():
    root = Path(__file__).resolve().parents[2] / "Assets/EndfieldShaderPack"
    helper = (root / "EndfieldOfficialSkin.hlsl").read_text("utf-8-sig")
    for name in ("_BaseMap", "_HighlightMap"):
        assert (
            "SAMPLE_TEXTURE2D_BIAS(" + name + ", sampler_Endfield_LinearRepeat,"
            in helper
        )
    for name in ("_ShadowLutTex", "_SDFLightmap", "_DiffRampMap"):
        assert (
            "SAMPLE_TEXTURE2D_LOD(" + name + ", sampler_Endfield_LinearClamp," in helper
        )
    assert "SAMPLE_TEXTURE2D_BIAS(_SDFMask, sampler_Endfield_LinearClamp," in helper
    assert "zero source _GlobalMipBias" not in helper
    shader = (root / "EndfieldCharacterLit.shader").read_text("utf-8-sig")
    assert "EndfieldShadeOfficialSkin(sourceUV, albedo," in shader


class SkinFixture(Fixture):
    """API/IO fixture only; real native evidence is the offline GPU replay."""

    def __init__(self, fail=""):
        super().__init__(fail)
        self.event = 786

    @staticmethod
    def format_for(role):
        return (
            "BC5_UNORM"
            if role == "Normal"
            else "BC7_SRGB"
            if role in ("Base", "ShadowLUT", "Emotion")
            else "R8G8B8A8_UNORM"
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
            for role in skin.SAMPLERS
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


def test_actual_skin_plan_collects_typed_views_and_role_samplers():
    fixture = SkinFixture()
    with (
        tempfile.TemporaryDirectory() as folder,
        patch.object(core, "ROLES", skin.ROLES),
        patch.object(core, "PROGRAMS", skin.PROGRAMS),
        patch.object(core, "sampler_record", side_effect=lambda s: sampler(s.number)),
    ):
        records = core.collect(
            fixture.rd, fixture, Path(folder), skin.ROLES, skin.PROGRAMS, skin.SAMPLERS
        )
        assert len(records) == 12
        for record in records:
            assert record["sampler"]["binding"] == skin.SAMPLERS[record["role"]]
            assert record["sample_cast"] == (
                "CompType.UNormSRGB"
                if record["role"] in ("ShadowLUT", "Base", "Emotion")
                else "CompType.UNorm"
            )
            assert len(record["native_samples"]) == 10
            assert (Path(folder) / record["file"]).stat().st_size == record["bytes"]


def test_unmatched_plan_rejected_before_replay():
    with pytest.raises(ValueError, match="exact PS identity"):
        core.collect(None, None, None, skin.ROLES, {786: 22250}, skin.SAMPLERS)


def test_renderdoc_entry_forwards_exact_plan_then_exits():
    with patch.object(core, "run") as run, pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(skin.__file__)), run_name="__main__")
    assert stopped.value.code is None
    run.assert_called_once_with(skin.ROLES, skin.PROGRAMS, skin.SAMPLERS)


@pytest.mark.parametrize("failure", ["", "shader", "shutdown", "truncated"])
def test_skin_completion_requires_successful_replay_and_shutdown(failure):
    fixture = SkinFixture(failure)
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
            patch.dict(sys.modules, renderdoc=fixture.rd),
            patch.object(
                core,
                "open_controller",
                return_value=(NS(Shutdown=lambda: None), fixture),
            ),
            patch.object(core, "ROLES", skin.ROLES),
            patch.object(core, "PROGRAMS", skin.PROGRAMS),
            patch.object(
                core, "sampler_record", side_effect=lambda s: sampler(s.number)
            ),
        ):
            if failure:
                with pytest.raises((ValueError, RuntimeError)):
                    skin.run()
                assert (output / "error.json").exists()
                assert not (output / "complete.json").exists()
            else:
                skin.run()
                assert (output / "complete.json").exists()
            assert fixture.closed
