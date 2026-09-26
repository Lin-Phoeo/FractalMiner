import importlib.util
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest


MODULE = Path(__file__).parents[1] / "export_pmx_motion_rig.py"
SPEC = importlib.util.spec_from_file_location("export_pmx_motion_rig", MODULE)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


def vec(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


def bone(name, parent=-1, flag=0, effect=-1, ik=None):
    return SimpleNamespace(name=name, position=vec(1, 2, 3), parent_index=parent,
                           layer=0, flag=flag, effect_index=effect, effect_factor=.5,
                           fixed_axis=vec(0, 1, 0), ik=ik)


def test_exports_parent_grant_and_ik_links():
    link = SimpleNamespace(bone_index=0, limit_angle=1,
                           limit_min=vec(-1, 0, 0), limit_max=vec(0, 0, 0))
    ik = SimpleNamespace(target_index=0, loop=12, limit_radian=.4, link=[link])
    model = SimpleNamespace(name="test", bones=[bone("全ての親"),
                            bone("左足ＩＫ", 0, 0x0120, 0, ik)])
    data = EXPORT.export_rig(model)
    item = data["bones"][1]
    assert item["name"] == "左足IK"
    assert item["rest"] == [1, 2, 3]
    assert item["grant"] == 0 and item["grantRotation"] is True
    assert item["effector"] == 0 and item["iterations"] == 12
    assert item["links"][0]["minimum"] == [-1, 0, 0]


def test_rejects_invalid_parent_index():
    model = SimpleNamespace(name="bad", bones=[bone("x", 3)])
    with pytest.raises(ValueError, match="parent"):
        EXPORT.export_rig(model)


def test_export_paths_never_overwrite_model_or_existing_output(tmp_path):
    model = tmp_path / "model.pmx"
    model.write_bytes(b"PMX ")
    with pytest.raises(ValueError, match="same file"):
        EXPORT.validate_paths(model, model, False)
    output = tmp_path / "rig.json"
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        EXPORT.validate_paths(model, output, False)
    EXPORT.validate_paths(model, output, True)


def test_main_exports_without_real_pmx_dependency(tmp_path, monkeypatch):
    model = tmp_path / "model.pmx"
    model.write_bytes(b"PMX ")
    output = tmp_path / "rig.json"
    fake_reader = types.ModuleType("pymeshio.pmx.reader")
    fake_reader.read_from_file = lambda _: SimpleNamespace(name="test", bones=[bone("全ての親")])
    fake_pmx = types.ModuleType("pymeshio.pmx")
    fake_pmx.reader = fake_reader
    fake_package = types.ModuleType("pymeshio")
    fake_package.pmx = fake_pmx
    monkeypatch.setitem(sys.modules, "pymeshio", fake_package)
    monkeypatch.setitem(sys.modules, "pymeshio.pmx", fake_pmx)
    monkeypatch.setitem(sys.modules, "pymeshio.pmx.reader", fake_reader)
    monkeypatch.setattr(sys, "argv", ["export", str(model), str(output)])
    EXPORT.main()
    assert json.loads(output.read_text(encoding="utf-8"))["bones"][0]["name"] == "全ての親"


def test_export_rejects_duplicate_names_and_self_grant():
    with pytest.raises(ValueError, match="duplicate"):
        EXPORT.export_rig(SimpleNamespace(name="bad", bones=[bone("x"), bone("x")]))
    with pytest.raises(ValueError, match="itself"):
        EXPORT.export_rig(SimpleNamespace(name="bad", bones=[bone("x", flag=0x100, effect=0)]))
