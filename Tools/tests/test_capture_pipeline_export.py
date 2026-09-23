import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture_pipeline_export as export


class PipelineExportTests(unittest.TestCase):
    def test_plan_only_known_offline_resources(self):
        self.assertEqual({p['id'] for p in export.PLAN}, {14188, 58932, 19397, 19394, 58923, 19599})
        self.assertEqual(next(p for p in export.PLAN if p['id']==14188)['event'], 835)

    def test_cube_saves_all_slices_and_mips(self):
        rd=NS(TextureSave=lambda:NS(slice=NS(sliceIndex=0)),FileType=NS(DDS='dds',EXR='exr'),
              ResultCode=NS(Succeeded='ok'))
        controller=Mock()
        def save(settings,path):
            Path(path).write_bytes(b'DDS '+b'\0'*144)
            self.assertEqual(settings.mip,-1)
            self.assertEqual(settings.slice.sliceIndex,-1)
            return 'ok'
        controller.SaveTexture.side_effect=save
        with tempfile.TemporaryDirectory() as folder:
            result=export.save_texture(rd,controller,'rid',Path(folder)/'cube.dds','DDS',True)
            self.assertEqual(result['bytes'],148)

    def test_save_failure_does_not_report_success(self):
        rd=NS(TextureSave=lambda:NS(slice=NS(sliceIndex=0)),FileType=NS(DDS='dds'),ResultCode=NS(Succeeded='ok'))
        controller=Mock();controller.SaveTexture.return_value='failed'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                export.save_texture(rd,controller,'rid',Path(folder)/'x.dds','DDS',False)

    def test_refuses_overwriting_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x.dds';path.write_bytes(b'existing')
            with self.assertRaises(FileExistsError):export.save_texture(None,None,None,path,'DDS',False)
            self.assertEqual(path.read_bytes(),b'existing')

    def test_rejects_wrong_capture_layout(self):
        plan=export.PLAN[0]
        wrong=NS(width=128,height=128,arraysize=1,mips=8,format=NS(Name=lambda:'BC6_UFLOAT'))
        with self.assertRaises(ValueError):export.validate_texture(wrong,plan)


if __name__=='__main__':unittest.main()
