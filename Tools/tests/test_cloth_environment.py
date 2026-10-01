"""BC6 native input contracts; synthetic blocks are not captured truth."""

import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_cloth_environment as export

ROOT = Path(__file__).resolve().parents[2]


class CubeContracts(unittest.TestCase):
    def test_layout_all_faces_and_small_mips(self):
        rows = export.cube_layout()
        self.assertEqual(len(rows), 48)
        self.assertEqual(sum(r["bytes"] for r in rows), 131232)
        self.assertEqual(
            rows[-1], {"face": 5, "mip": 7, "width": 1, "offset": 131216, "bytes": 16}
        )
        self.assertEqual(
            [r["bytes"] for r in rows[:8]], [16384, 4096, 1024, 256, 64, 16, 16, 16]
        )

    def test_each_draw_time_face_mip_equals_dds(self):
        rows = export.cube_layout()
        payload = bytes(range(256)) * (131232 // 256) + bytes(range(131232 % 256))
        levels = [payload[r["offset"] : r["offset"] + r["bytes"]] for r in rows]
        export.verify_payload(levels, payload)
        for corrupt in ("truncated", "extra", "swapped"):
            bad = list(levels)
            if corrupt == "truncated":
                bad[-1] = bad[-1][:-1]
            elif corrupt == "extra":
                bad.append(b"x")
            else:
                bad[0] = bytes([bad[0][0] ^ 1]) + bad[0][1:]
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                export.verify_payload(bad, payload)

    def test_identity_cube_view(self):
        good = export.EXPECTED_VIEW.copy()
        export.validate_view(good)
        for key, value in [
            ("firstMip", 1),
            ("numMips", 1),
            ("numSlices", 1),
            ("format", "BC6_SFLOAT"),
            ("swizzle", ["TextureSwizzle.Blue"] * 4),
            ("minLODClamp", 1),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                export.validate_view(dict(good, **{key: value}))

    def test_sampler_rejects_trilinear_repeat_and_bias(self):
        good = export.EXPECTED_SAMPLER.copy()
        export.validate_sampler(good)
        for key, value in [
            ("filter", dict(good["filter"], mip="FilterMode.Linear")),
            ("addressU", "AddressMode.Wrap"),
            ("mipBias", -1),
            ("unnormalized", True),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                export.validate_sampler(dict(good, **{key: value}))

    def test_source_uses_captured_clamp_sampler(self):
        code = (
            ROOT / "Assets/EndfieldShaderPack/EndfieldOfficialCloth.hlsl"
        ).read_text("utf-8-sig")
        self.assertIn(
            "SAMPLE_TEXTURECUBE_LOD(_CharMaxCubemap, sampler_Endfield_LinearClamp,",
            code,
        )
        self.assertIn("1.2 * log2(max(roughness, 0.001)) + 5.0", code)

    def test_native_cube_upload_not_saved_or_regenerated(self):
        code = (
            ROOT / "Assets/EndfieldShaderPack/EndfieldCapturedEnvironment.cs"
        ).read_text("utf-8-sig")
        for required in (
            "TextureFormat.BC6H",
            "SetPixelData",
            "Apply(false, false)",
            "FilterMode.Bilinear",
            "TextureWrapMode.Clamp",
            "SHA256.Create()",
            "131380",
        ):
            self.assertIn(required, code)
        for forbidden in ("Compress(", "SetPixels(", "CreateAsset(", "SaveAssets("):
            self.assertNotIn(forbidden, code)

    def test_scoped_pose_entry_and_manifest_pin(self):
        pose = (
            ROOT / "Assets/EndfieldShaderPack/Editor/EndfieldPoseApplyValidation.cs"
        ).read_text("utf-8-sig")
        self.assertIn("EndfieldCapturedEnvironmentInputs.BindIfRequested(report)", pose)
        code = (
            ROOT
            / "Assets/EndfieldShaderPack/Editor/EndfieldCapturedEnvironmentInputs.cs"
        ).read_text("utf-8-sig")
        for required in (
            "ManifestSha256",
            "IDisposable",
            "GetGlobalTexture",
            "SetGlobalTexture",
            "ENDFIELD_NATIVE_ENVIRONMENT_INPUTS",
        ):
            self.assertIn(required, code)
        for forbidden in ("SaveScene(", "SaveAssets(", "SaveAndReimport("):
            self.assertNotIn(forbidden, code)


class ReplayFixture:
    """Independent API/IO harness only; not a shader/native fidelity oracle."""

    def __init__(self, failure=""):
        self.failure, self.event, self.closed = failure, 835, False
        self.rd = NS(
            ShaderStage=NS(Pixel="ShaderStage.Pixel"),
            CompType=NS(Float="float"),
            DescriptorType=NS(Sampler="sampler", ImageSampler="image-sampler"),
            Subresource=lambda mip, face, sample: NS(mip=mip, face=face),
            DescriptorRange=lambda access: access,
        )
        payload = bytearray(131380)
        for offset, value in {
            0: 0x20534444,
            4: 124,
            12: 128,
            16: 128,
            28: 8,
            84: 0x30315844,
            128: 95,
            132: 3,
            136: 4,
            140: 1,
        }.items():
            struct.pack_into("<I", payload, offset, value)
        self.dds = bytes(payload)

    def access(self):
        return NS(
            index=0,
            descriptorStore="store",
            byteOffset=45,
            byteSize=1,
            arrayElement=0,
            stage="ShaderStage.Pixel",
            type="image",
            staticallyUnused=False,
        )

    def GetFrameInfo(self):
        return NS(frameNumber=0 if self.failure == "frame" else 6411)

    def GetTextures(self):
        return [
            NS(
                resourceId="ResourceId::14188",
                width=128,
                height=128,
                depth=1,
                arraysize=6,
                mips=8,
                format=NS(
                    Name=lambda: "BAD" if self.failure == "format" else "BC6_UFLOAT"
                ),
            )
        ]

    def SetFrameEvent(self, event, force):
        self.event = event

    def GetPipelineState(self):
        return self

    def GetShader(self, stage):
        return "ResourceId::" + str(
            0 if self.failure == "shader" else (22255 if self.event == 835 else 37669)
        )

    def GetShaderReflection(self, stage):
        return NS(
            rawBytes=b"fixture",
            readOnlyResources=[
                NS(fixedBindSetOrSpace=0, fixedBindNumber=45, name="cube")
            ],
            samplers=[NS(fixedBindSetOrSpace=0, fixedBindNumber=6, name="sampler")],
        )

    def GetReadOnlyResources(self, stage):
        if self.failure == "missing-binding":
            return []
        view = export.EXPECTED_VIEW.copy()
        view["swizzle"] = NS(
            **{
                c: "TextureSwizzle." + c.title()
                for c in ("red", "green", "blue", "alpha")
            }
        )
        view["resource"] = (
            "ResourceId::0" if self.failure == "resource" else "ResourceId::14188"
        )
        view["view"] = "view"
        view["format"] = NS(Name=lambda: "BC6_UFLOAT")
        if self.failure == "view":
            view["numMips"] = 1
        return [NS(access=self.access(), descriptor=NS(**view))]

    def GetSamplers(self, stage):
        return [] if self.failure == "missing-sampler" else [NS(access=self.access())]

    def GetSamplerDescriptors(self, store, ranges):
        return [] if self.failure == "unresolved-sampler" else [NS(type="sampler")]

    def GetTextureData(self, resource, subresource):
        row = export.cube_layout()[subresource.face * 8 + subresource.mip]
        data = self.dds[148 + row["offset"] : 148 + row["offset"] + row["bytes"]]
        return data[:-1] if self.failure == "truncated-mip" else data

    def PickPixel(self, *args):
        return NS(floatValue=[0.1, 0.2, 0.3, 1])

    def Shutdown(self):
        self.closed = True
        if self.failure == "shutdown":
            raise RuntimeError("shutdown failure")


class OfflineExportContracts(unittest.TestCase):
    def test_collect_and_reject_incomplete_resources(self):
        fixture = ReplayFixture()
        with patch.object(
            export, "sampler_record", return_value=export.EXPECTED_SAMPLER.copy()
        ):
            result = export.collect(fixture.rd, fixture, fixture.dds)
            self.assertEqual([r["event"] for r in result], [835, 850])
            self.assertTrue(all(len(r["native_samples"]) == 144 for r in result))
            for failure in (
                "frame",
                "format",
                "shader",
                "missing-binding",
                "resource",
                "view",
                "missing-sampler",
                "unresolved-sampler",
                "truncated-mip",
            ):
                bad = ReplayFixture(failure)
                with self.subTest(failure=failure), self.assertRaises(ValueError):
                    export.collect(bad.rd, bad, bad.dds)

    def test_dds_header_size_hash_and_completion_after_shutdown(self):
        for failure in ("", "shader", "shutdown", "header", "hash", "length"):
            fixture = ReplayFixture(failure)
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                capture = root / "fixture.rdc"
                capture.write_bytes(b"offline fixture")
                dds = fixture.dds
                if failure == "header":
                    dds = bytes([0]) + dds[1:]
                elif failure == "length":
                    dds = dds[:-1]
                source = root / "fixture.dds"
                source.write_bytes(dds)
                output = root / "out"
                env = {
                    "ENDFIELD_CAPTURE_PATH": str(capture),
                    "ENDFIELD_CAPTURE_OUTPUT": str(output),
                    "ENDFIELD_ENVIRONMENT_DDS": str(source),
                }
                with (
                    patch.dict(os.environ, env),
                    patch.dict(sys.modules, {"renderdoc": fixture.rd}),
                    patch.object(
                        export,
                        "open_controller",
                        return_value=(NS(Shutdown=lambda: None), fixture),
                    ),
                    patch.object(
                        export,
                        "DDS_SHA256",
                        hashlib.sha256(dds).hexdigest()
                        if failure != "hash"
                        else "wrong",
                    ),
                    patch.object(
                        export,
                        "sampler_record",
                        return_value=export.EXPECTED_SAMPLER.copy(),
                    ),
                ):
                    if failure:
                        with self.assertRaises((ValueError, RuntimeError)):
                            export.run()
                        self.assertFalse((output / "complete.json").exists())
                        self.assertTrue((output / "error.json").is_file())
                    else:
                        export.run()
                        self.assertTrue(fixture.closed)
                        self.assertEqual(
                            json.loads((output / "complete.json").read_text())[
                                "status"
                            ],
                            "ok",
                        )
                        self.assertEqual(
                            (output / "character-environment.dds").read_bytes(), dds
                        )
                        with self.assertRaises(FileExistsError):
                            export.run()


if __name__ == "__main__":
    unittest.main()
