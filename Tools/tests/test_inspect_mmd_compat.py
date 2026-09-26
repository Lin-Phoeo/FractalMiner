import importlib.util
from pathlib import Path
import struct

import pytest


MODULE = Path(__file__).parents[1] / "inspect_mmd_compat.py"
SPEC = importlib.util.spec_from_file_location("inspect_mmd_compat", MODULE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_vmd_track_names_and_count(tmp_path):
    header = b"Vocaloid Motion Data 0002".ljust(30, b"\0")
    model = "テスト".encode("cp932").ljust(20, b"\0")
    bone = "左足ＩＫ".encode("cp932").ljust(15, b"\0")
    path = tmp_path / "motion.vmd"
    path.write_bytes(header + model + struct.pack("<I", 1) + bone + bytes(96))

    name, tracks, count = AUDIT.vmd_tracks(path)
    assert name == "テスト"
    assert tracks == {"左足ＩＫ"}
    assert count == 1


def test_vmd_rejects_truncated_frame(tmp_path):
    path = tmp_path / "broken.vmd"
    path.write_bytes(b"Vocaloid Motion Data 0002".ljust(30, b"\0") +
                     bytes(20) + struct.pack("<I", 1) + bytes(110))
    with pytest.raises(ValueError, match="Truncated VMD"):
        AUDIT.vmd_tracks(path)
