"""Importer boundary checks; runtime verification lives in its Unity entry point."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "Assets/EndfieldShaderPack/Editor/EndfieldMaterialImporter.cs"


def test_skin_ramp_and_highlight_are_data_slots_not_srgb_colours():
    source = SOURCE.read_text(encoding="utf-8")
    slots = source.split("DataTextureSlots =", 1)[1].split("};", 1)[0]
    assert '"_DiffRampMap"' in slots
    assert '"_HighlightMap"' in slots


def test_targeted_repair_backs_up_metadata_and_checks_runtime_format():
    source = SOURCE.read_text(encoding="utf-8")
    assert "RepairCapturedSkinDataTextureImports" in source
    assert "GraphicsFormatUtility.IsSRGBFormat" in source
    assert "skin-data-texture-backup-" in source
    assert 'Path.Combine(Application.dataPath, "..", "Logs"' in source
