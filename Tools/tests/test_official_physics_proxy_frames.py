"""Native caller/Job fixtures; do not certify live Unity physics."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_bindpose import prepare_bound_bone_inputs
from official_physics_proxy_frames import (
    apply_bone_transform_flags,
    default_normal_adjustments,
    prepare_bone_proxy_frames,
    vertex_bindpose_frames,
    vertex_to_transform_rotations,
)
from official_physics_snapshot import TransformGetterValues

I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
Q = (0, 0, 0, 1)
UP, FORWARD = (0, 1, 0), (0, 0, 1)


def test_default_fill_is_identity_per_vertex_not_zero():
    assert default_normal_adjustments(3, 0) == (Q, Q, Q)
    assert default_normal_adjustments(0, 0) == ()


@pytest.mark.parametrize("mode", [1, 2, 3, -1, True])
def test_unported_alignment_modes_are_not_silently_treated_as_none(mode):
    with pytest.raises(ValueError):
        default_normal_adjustments(1, mode)


@pytest.mark.parametrize("count", [-1, 65537, 1.5, True])
def test_invalid_default_buffer_count_is_adapter_rejection(count):
    with pytest.raises(ValueError):
        default_normal_adjustments(count, 0)


def test_vertex_bindpose_stores_negative_position_separately_from_inverse_frame():
    result = vertex_bindpose_frames([(2, 3, 4)], [(-1, 0, 0)], [FORWARD])
    assert result.positions == ((-2, -3, -4),)
    assert result.rotations[0] == pytest.approx((0, 0, -(2**-0.5), 2**-0.5))
    # NOT a conventional inverse TRS translation (which would rotate -position).
    assert result.positions[0] != (-3, 2, -4)


def test_bindpose_position_sign_bit_is_flipped_including_zero():
    result = vertex_bindpose_frames([(0.0, -0.0, 2**-149)], [UP], [FORWARD])
    assert struct.pack("<3f", *result.positions[0]).hex() == (
        "000000800000000001000080"
    )


def test_binding_rotation_uses_reciprocal_squared_norm_not_normalized_conjugate():
    result = vertex_bindpose_frames([(0, 0, 0)], [UP], [(0, 0, 2)])
    # Non-unit forward is intentionally retained by the original frame helper.
    q = result.rotations[0]
    assert q == pytest.approx((0, 0, 0, 1), abs=2e-7)
    assert struct.pack("<4f", *q)[:12] == b"\x00\x00\x00\x80" * 3


def test_independent_unmodified_managed_library_raw_bit_fixture():
    # Standalone .NET + original local Unity.Mathematics DLL, scalar FP enabled.
    normal, tangent = (0.3, 0.7, 0.9), (-0.2, 0.3, 1.2)
    inverse = vertex_bindpose_frames([(0, 0, 0)], [normal], [tangent]).rotations[0]
    output = vertex_to_transform_rotations(
        (0.2, -0.1, 0.3, 0.8), [normal], [tangent], [(0.3, 0.1, -0.4, 1.2)]
    )[0]
    assert struct.unpack("<4i", struct.pack("<4f", *inverse)) == (
        1035650230,
        1039030499,
        1052657578,
        1063952778,
    )
    assert struct.unpack("<4i", struct.pack("<4f", *output)) == (
        1057051694,
        1054042577,
        1054283816,
        1062849390,
    )


def test_vertex_to_transform_rotation_preserves_nonunit_world_quaternion():
    result = vertex_to_transform_rotations(Q, [UP], [FORWARD], [(0, 0, 0, 2)])
    assert result == ((0, 0, 0, 2),)


def test_transform_order_is_inverse_frame_times_inverse_render_times_world():
    # Exact 180-degree axes make swapped multiplication visibly wrong.
    result = vertex_to_transform_rotations(
        (1, 0, 0, 0), [UP], [FORWARD], [(0, 1, 0, 0)]
    )
    assert result == ((0, 0, 1, 0),)


def test_frame_offset_is_removed_without_guessing_children_or_axes():
    result = vertex_to_transform_rotations(Q, [(-1, 0, 0)], [FORWARD], [(0, 0, 1, 1)])
    assert result[0] == pytest.approx((0, 0, 0, 2**0.5), abs=2e-7)


@pytest.mark.parametrize(
    "attribute, expected", [(0, 0), (1, 10), (2, 12), (3, 12), (4, 0), (255, 12)]
)
def test_flags_moving_has_priority_over_fixed_and_bits_are_not_cleared(
    attribute, expected
):
    assert apply_bone_transform_flags([attribute], [0]) == (expected,)
    assert apply_bone_transform_flags([attribute], [241]) == (241 | expected,)


def test_flags_do_not_mutate_caller_buffers():
    attributes, flags = [1, 2, 0], [0, 0, 255]
    assert apply_bone_transform_flags(attributes, flags) == (10, 12, 255)
    assert attributes == [1, 2, 0] and flags == [0, 0, 255]


@pytest.mark.parametrize("a,f", [([1], []), ([1], [256]), ([-1], [0]), ([True], [0])])
def test_flag_mismatch_or_invalid_byte_is_refused(a, f):
    with pytest.raises(ValueError):
        apply_bone_transform_flags(a, f)


def test_explicit_bound_snapshot_to_proxy_frame_composition():
    getters = [
        TransformGetterValues((2, 0, 0), Q, I, (2, 0, 0), Q),
        TransformGetterValues((2, 1, 0), Q, I, (0, 1, 0), Q),
    ]
    bound = prepare_bound_bone_inputs(getters, I, I, [-1, 0], [0])
    result = prepare_bone_proxy_frames(bound, Q, [1, 1], alignment_mode=0)
    assert result.bound is bound
    assert result.normal_adjustments == (Q, Q)
    assert result.vertex_bindposes.positions == ((-2, 0, 0), (-2, -1, 0))
    assert result.vertex_to_transform_rotations == (Q, Q)
    assert result.transform_flags == (11, 13)
    assert bound.inputs.selection.attributes == (1, 2)


def test_empty_job_buffers_return_empty_outputs():
    assert vertex_bindpose_frames([], [], []).positions == ()
    assert vertex_to_transform_rotations(Q, [], [], []) == ()
    assert apply_bone_transform_flags([], []) == ()
    bound = prepare_bound_bone_inputs([], I, I, [], [])
    assert prepare_bone_proxy_frames(bound, Q, []).transform_flags == ()


@pytest.mark.parametrize("normal,tangent", [((0, 0, 0), FORWARD), (UP, UP)])
def test_degenerate_frame_is_refused_not_look_rotation_safe(normal, tangent):
    with pytest.raises(ValueError):
        vertex_bindpose_frames([(0, 0, 0)], [normal], [tangent])


@pytest.mark.parametrize("buffer", [float("nan"), float("inf"), 1e40, True])
def test_nonfinite_or_unrepresentable_position_is_refused(buffer):
    with pytest.raises(ValueError):
        vertex_bindpose_frames([(buffer, 0, 0)], [UP], [FORWARD])


def test_parallel_frame_buffers_and_rotation_are_validated_even_for_empty_input():
    with pytest.raises(ValueError):
        vertex_bindpose_frames([(0, 0, 0)], [], [FORWARD])
    with pytest.raises(ValueError):
        vertex_to_transform_rotations(Q, [UP], [], [Q])
    with pytest.raises(ValueError):
        vertex_to_transform_rotations((float("nan"), 0, 0, 1), [], [], [])


def test_composition_refuses_unported_alignment_instead_of_modifying_frames():
    bound = prepare_bound_bone_inputs([], I, I, [], [])
    with pytest.raises(ValueError):
        prepare_bone_proxy_frames(bound, Q, [], alignment_mode=1)
