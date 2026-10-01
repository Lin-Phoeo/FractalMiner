"""Actual variant material-input contracts; not screenshot fitting."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_cloth_materials as export


class MaterialContracts(unittest.TestCase):
    def test_global_weather_binding_set_is_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                export.collect(None, None, Path(folder), resource_set=2)
            fixture = Fixture()
            original = fixture.GetShaderReflection
            def global_reflection(stage):
                result = original(stage)
                for resource in result.readOnlyResources:
                    resource.fixedBindSetOrSpace = 0
                return result
            fixture.GetShaderReflection = global_reflection
            with patch.object(export, "sampler_record", side_effect=lambda value: sampler(value.number)):
                records = export.collect(fixture.rd, fixture, Path(folder), resource_set=0)
            self.assertEqual(len(records), 9)
            self.assertTrue(all(record["binding"]["set"] == 0 for record in records))

    def test_variant_roles_do_not_invent_cloth01_emission_or_shadow_lut(self):
        self.assertEqual(
            export.ROLES[835], {"SpecRamp": 1, "P": 2, "DiffRamp": 3, "Base": 5}
        )
        self.assertEqual(
            export.ROLES[850], {"SpecRamp": 1, "P": 2, "E": 3, "DiffRamp": 4, "Base": 6}
        )

    def test_payload_layout_preserves_small_compressed_mips(self):
        self.assertEqual(export.level_bytes(2, 1, "BC7_UNORM"), 16)
        self.assertEqual(export.level_bytes(2, 1, "BC1_SRGB"), 8)
        self.assertEqual(export.level_bytes(16, 16, "R8G8B8A8_UNORM"), 1024)
        with self.assertRaises(ValueError):
            export.level_bytes(16, 16, "unreviewed")
        for width in (0, -1, True):
            with self.assertRaises(ValueError):
                export.level_bytes(width, 1, "BC7_UNORM")

    def test_view_format_can_change_srgb_not_dimensions_or_channels(self):
        image = {
            "width": 2048,
            "height": 2048,
            "depth": 1,
            "arraysize": 1,
            "mips": 12,
            "format": "BC7_UNORM",
        }
        good = {
            "format": "BC7_SRGB",
            "textureType": "TextureType.Texture2D",
            "firstMip": 0,
            "numMips": 12,
            "firstSlice": 0,
            "numSlices": 1,
            "minLODClamp": 0,
            "swizzle": export.IDENTITY,
        }
        export.validate_view(image, good)
        for key, value in [
            ("numMips", 1),
            ("firstMip", 1),
            ("format", "BC1_UNORM"),
            ("swizzle", ["bad"] * 4),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                export.validate_view(image, dict(good, **{key: value}))


def sampler(number):
    address = "AddressMode.Wrap" if number == 4 else "AddressMode.ClampEdge"
    return {
        "addressU": address,
        "addressV": address,
        "addressW": address,
        "filter": {
            "minify": "FilterMode.Linear",
            "magnify": "FilterMode.Linear",
            "mip": "FilterMode.Point",
            "filter": "FilterFunction.Normal",
        },
        "maxAnisotropy": 0,
        "minLOD": 0,
        "maxLOD": 1000,
        "mipBias": 0,
        "unnormalized": False,
        "compareFunction": "CompareFunction.Never",
    }


class Fixture:
    """API/IO fixture, never native GPU fidelity evidence."""

    def __init__(self, fail=""):
        self.fail, self.event, self.closed = fail, 835, False
        self.rd = NS(
            ShaderStage=NS(Pixel="ShaderStage.Pixel"),
            DescriptorType=NS(Sampler="sampler", ImageSampler="image-sampler"),
            Subresource=lambda mip, layer, sample: NS(mip=mip),
            DescriptorRange=lambda access: access,
            CompType=NS(UNorm="CompType.UNorm", UNormSRGB="CompType.UNormSRGB"),
        )
        self.casts = []

    def access(self, index):
        return NS(
            index=index,
            descriptorStore="store",
            byteOffset=17,
            byteSize=1,
            arrayElement=0,
            stage="pixel",
            type="image",
            staticallyUnused=False,
        )

    def GetFrameInfo(self):
        return NS(frameNumber=0 if self.fail == "frame" else 6411)

    def GetTextures(self):
        return [
            NS(
                resourceId=role,
                width=4,
                height=4,
                depth=1,
                arraysize=1,
                mips=2,
                format=NS(
                    Name=lambda role=role: (
                        "BC7_SRGB" if role in ("Base", "E") else "R8G8B8A8_UNORM"
                    )
                ),
            )
            for role in ("Base", "P", "E", "DiffRamp", "SpecRamp")
        ]

    def SetFrameEvent(self, event, force):
        self.event = event

    def GetPipelineState(self):
        return self

    def GetShader(self, stage):
        return "ResourceId::" + str(
            0 if self.fail == "shader" else export.PROGRAMS[self.event]
        )

    def GetShaderReflection(self, stage):
        return NS(
            rawBytes=b"fixture",
            readOnlyResources=[
                NS(fixedBindNumber=n, fixedBindSetOrSpace=1, name=r)
                for r, n in export.ROLES[self.event].items()
            ],
            samplers=[
                NS(fixedBindNumber=n, fixedBindSetOrSpace=0, name="s") for n in (4, 6)
            ],
        )

    def GetReadOnlyResources(self, stage):
        if self.fail == "missing":
            return []
        used = []
        for i, role in enumerate(export.ROLES[self.event]):
            used.append(
                NS(
                    access=self.access(i),
                    descriptor=NS(
                        resource=role,
                        view="view",
                        textureType="TextureType.Texture2D",
                        format=NS(
                            Name=lambda role=role: (
                                "BC7_SRGB"
                                if role in ("Base", "E")
                                else "R8G8B8A8_UNORM"
                            )
                        ),
                        firstMip=0,
                        numMips=2,
                        firstSlice=0,
                        numSlices=1,
                        minLODClamp=0,
                        swizzle=NS(
                            **{
                                c: "TextureSwizzle." + c.title()
                                for c in ("red", "green", "blue", "alpha")
                            }
                        ),
                    ),
                )
            )
        return used + used[:1] if self.fail == "duplicate" else used

    def GetSamplers(self, stage):
        used = [NS(access=self.access(i)) for i in (0, 1)]
        return (
            []
            if self.fail == "missing-sampler"
            else used + used[:1]
            if self.fail == "duplicate-sampler"
            else used
        )

    def GetSamplerDescriptors(self, store, ranges):
        return (
            []
            if self.fail == "unresolved"
            else [NS(type="sampler", number=4 if ranges[0].index == 0 else 6)]
        )

    def GetTextureData(self, resource, sub):
        size = export.level_bytes(
            max(1, 4 >> sub.mip),
            max(1, 4 >> sub.mip),
            "BC7_SRGB" if resource in ("Base", "E") else "R8G8B8A8_UNORM",
        )
        return b"x" * (size - (1 if self.fail == "truncated" else 0))

    def PickPixel(self, resource, x, y, sub, cast):
        self.casts.append((resource, cast))
        return NS(floatValue=[0.1, 0.2, 0.3, 0.4])

    def Shutdown(self):
        self.closed = True
        if self.fail == "shutdown":
            raise RuntimeError("shutdown failed")


class OfflineContracts(unittest.TestCase):
    def patched_sampler(self, value):
        result = sampler(value.number)
        if self.fixture.fail == "sampler-state":
            result["mipBias"] = -1
        return result

    def collect(self, fixture, output):
        self.fixture = fixture
        with patch.object(export, "sampler_record", side_effect=self.patched_sampler):
            return export.collect(fixture.rd, fixture, output)

    def test_collect_preserves_bytes_identity_and_casts(self):
        f = Fixture()
        with tempfile.TemporaryDirectory() as folder:
            records = self.collect(f, Path(folder))
            self.assertEqual(len(records), 9)
            for record in records:
                data = (Path(folder) / record["file"]).read_bytes()
                self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(len(record["native_samples"]), 10)
            self.assertTrue(
                all(
                    cast
                    == (
                        "CompType.UNormSRGB" if r in ("Base", "E") else "CompType.UNorm"
                    )
                    for r, cast in f.casts
                )
            )
            with self.assertRaises(FileExistsError):
                self.collect(f, Path(folder))

    def test_reject_bad_replay_contracts(self):
        for fail in (
            "frame",
            "shader",
            "missing",
            "duplicate",
            "missing-sampler",
            "duplicate-sampler",
            "unresolved",
            "truncated",
            "sampler-state",
        ):
            with (
                self.subTest(fail=fail),
                tempfile.TemporaryDirectory() as folder,
                self.assertRaises(ValueError),
            ):
                self.collect(Fixture(fail), Path(folder))

    def test_sampler_rejects_wrong_domains(self):
        for number in (4, 6):
            export.validate_sampler(sampler(number), number)
            for key, value in [
                ("addressU", "bad"),
                ("filter", {}),
                ("mipBias", -1),
                ("maxLOD", 0),
            ]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    export.validate_sampler(
                        dict(sampler(number), **{key: value}), number
                    )
        with self.assertRaises(ValueError):
            export.validate_sampler(sampler(4), 7)

    def test_completion_only_after_shutdown(self):
        for fail in ("", "shader", "shutdown"):
            f = Fixture(fail)
            self.fixture = f
            cap = NS(Shutdown=lambda: None)
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                capture = Path(folder) / "test.rdc"
                capture.write_bytes(b"offline fixture")
                output = Path(folder) / "out"
                with (
                    patch.dict(
                        export.os.environ,
                        ENDFIELD_CAPTURE_PATH=str(capture),
                        ENDFIELD_CAPTURE_OUTPUT=str(output),
                    ),
                    patch.dict(sys.modules, renderdoc=f.rd),
                    patch.object(export, "open_controller", return_value=(cap, f)),
                    patch.object(
                        export, "sampler_record", side_effect=self.patched_sampler
                    ),
                ):
                    if fail:
                        with self.assertRaises((ValueError, RuntimeError)):
                            export.run()
                        self.assertTrue((output / "error.json").exists())
                        self.assertFalse((output / "complete.json").exists())
                    else:
                        export.run()
                        self.assertTrue((output / "complete.json").exists())
                    self.assertTrue(f.closed)


if __name__ == "__main__":
    unittest.main()
