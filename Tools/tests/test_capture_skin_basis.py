import struct
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capture_skin_basis import decode_basis_record


def record(flags, base):
    result = bytearray(256)
    struct.pack_into('<16f', result, 0, 1,0,0,0, 0,1,0,0, 0,0,1,0, -300,300,-300,1)
    struct.pack_into('<I', result, 76, flags)
    struct.pack_into('<I', result, 80, base)
    return result


def test_bit16_reads_the_root_rows_not_first_skinning_bone_or_mesh_matrix():
    rows = struct.pack('<12f', 0,0,1,-300, 0,1,0,301, -1,0,0,-300)
    result = decode_basis_record(record(52, 123), rows, [-300,300,-300])
    assert result['source'] == 'skin-root-buffer'
    assert result['base_float4'] == 123
    assert result['rows_local_origin'] == [[0,0,1,0], [0,1,0,1], [-1,0,0,0]]


def test_without_bit16_uses_column_major_instance_matrix():
    result = decode_basis_record(record(32, 123), None, [-300,300,-300])
    assert result['source'] == 'instance-matrix'
    assert result['rows_local_origin'] == [[1,0,0,0], [0,1,0,0], [0,0,1,0]]


@pytest.mark.parametrize('raw,rows', [(b'', b''), (record(52,123), b''),
                                      (record(52,123), struct.pack('<12f', *([float('nan')]*12)))])
def test_truncated_or_nonfinite_input_is_rejected(raw, rows):
    with pytest.raises(ValueError):
        decode_basis_record(raw, rows, [-300,300,-300])
