import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_skin_world import evaluate_world, compare_vertices


def test_column_major_instance_rotation_follows_weighted_skinning():
    positions = np.array([[1., 0., 0.]])
    weights = np.array([[32768., 32767., 0., 0.]]) / 65535.
    slots = np.array([[0, 1, 0, 0]])
    palette = np.zeros((2, 3, 4))
    palette[:, :3, :3] = np.eye(3)
    palette[1, 1, 3] = 2
    instance = np.array([[0, 0, 1, -300], [0, 1, 0, 300], [-1, 0, 0, -300], [0, 0, 0, 1]])
    result = evaluate_world(positions, weights, slots, palette, instance.T.flatten())
    np.testing.assert_allclose(result, [[0, 2 * 32767 / 65535, -1]])


def test_missing_instance_yaw_cannot_pass_world_vertex_gate():
    result = compare_vertices([[1, 0, 0]], [[0, 0, -1]], 5e-5)
    assert not result['pass']
    assert result['max_m'] == pytest.approx(2**.5)


@pytest.mark.parametrize('actual,expected', [([], []), ([[float('nan'), 0, 0]], [[0, 0, 0]]),
                                          ([[0, 0, 0]], [[0, 0, 0], [1, 0, 0]])])
def test_invalid_vertex_comparisons_fail_closed(actual, expected):
    with pytest.raises(ValueError):
        compare_vertices(actual, expected, 5e-5)
