"""Source-gated Line frame production; no final proxy or native buffers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_line_frames import compose_line_proxy_frames


def fixture():
    return {
        "positions": ((2, 3, 4), (-1, 2, 0)),
        "normals": ((0, 1, 0),) * 2,
        "tangents": ((0, 0, 1),) * 2,
        "world_rotations": ((0, 0, 0, 1),) * 2,
        "inverse_render_rotation": (0, 0, 0, 1),
        "cloth_type": 1,
        "connect_mode": 0,
        "triangle_count": 0,
        "alignment_mode": 0,
    }


def test_identity_line_frames_no_extra_axis_rotation():
    result = compose_line_proxy_frames(**fixture())
    assert result.vertex_bindpose.positions == ((-2, -3, -4), (1, -2, 0))
    assert result.vertex_bindpose.rotations == ((0, 0, 0, 1),) * 2
    assert result.vertex_to_transform_rotations == ((0, 0, 0, 1),) * 2
    assert result.normal_adjustment_rotations == ((0, 0, 0, 1),) * 2
    assert result.source_vertex_indices == (0, 1)


def test_world_to_render_order_and_inverse_vertex_frame():
    values = fixture()
    # forward +X, up +Y => frame yaw +90, world rot identity.
    values["tangents"] = ((1, 0, 0),) * 2
    values["inverse_render_rotation"] = (0, 0, 1, 0)
    result = compose_line_proxy_frames(**values)
    assert result.vertex_bindpose.rotations[0] == pytest.approx(
        (0, -(2**-0.5), 0, 2**-0.5)
    )
    assert result.vertex_to_transform_rotations[0] == pytest.approx(
        (-(2**-0.5), 0, 2**-0.5, 0)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cloth_type", 0),
        ("cloth_type", 10),
        ("cloth_type", True),
        ("connect_mode", 1),
        ("triangle_count", 1),
        ("triangle_count", -1),
        ("alignment_mode", 1),
    ],
)
def test_unsupported_build_route_refused(field, value):
    values = fixture()
    values[field] = value
    with pytest.raises(ValueError):
        compose_line_proxy_frames(**values)


@pytest.mark.parametrize(
    "field", ["positions", "normals", "tangents", "world_rotations"]
)
def test_parallel_skin_window_required(field):
    values = fixture()
    values[field] = values[field][:-1]
    with pytest.raises(ValueError):
        compose_line_proxy_frames(**values)


def test_bad_direction_refused_no_artistic_fallback():
    values = fixture()
    values["tangents"] = values["normals"]
    with pytest.raises(ValueError):
        compose_line_proxy_frames(**values)


def test_empty_line_proxy():
    values = fixture()
    for field in ("positions", "normals", "tangents", "world_rotations"):
        values[field] = ()
    result = compose_line_proxy_frames(**values)
    assert result.vertex_bindpose.positions == result.normal_adjustment_rotations == ()
