"""Finite fixed-point center fixtures, not native execution or a full solver."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_cache import rotate_single
from official_physics_center_step import CenterStepState
from official_physics_frame_anchor import AnchorState, advance_frame_anchor
from official_physics_frame_inertia import FrameInertiaState, FrameInertiaTeam
from official_physics_frame_prelude import FramePreludeSettings, prepare_frame_inertia
from official_physics_frame_target import (
    ComponentFrameSample,
    FrameTargetBuffers,
    FrameTargetTeam,
    produce_frame_target,
    resolve_frame_target,
)
from official_physics_scale_remap import (
    ComponentScaleCache,
    prepare_component_scale_remap,
    prepare_frame_scale_matrices,
)

Q = (0.0, 0.0, 0.0, 1.0)
Z = (0.0, 0.0, 0.0)
S = (1.0, 1.0, 1.0)
Y = (0.0, 1.0, 0.0)
F = (0.0, 0.0, 1.0)
H = math.sqrt(0.5)
X90 = (H, 0, 0, H)
Y90 = (0, H, 0, H)
IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


def sample(**kw):
    return replace(ComponentFrameSample((99, 88, 77), Q, (2, 3, 4)), **kw)


def team(**kw):
    return replace(FrameTargetTeam(0, 1, 0, 1, S), **kw)


def buffers(**kw):
    return replace(FrameTargetBuffers((0,), ((2, 4, 6),), (Q,), (Q,)), **kw)


def run(c=None, t=None, b=None):
    return produce_frame_target(c or sample(), t or team(), b or buffers())


@pytest.mark.parametrize("count", [0, -1])
def test_count_nonpositive_uses_raw_component_pose_not_stage_or_identity(count):
    c = sample(position=(2**40 + 0.25, -3, 4), rotation=(0, 0, 0.5, 0.5))
    t = team(
        fixed_point_count=count,
        fixed_point_start=-123,
        proxy_chunk_start=-999,
        negative_scale_sign=math.nan,
        negative_scale_direction=(math.nan,) * 3,
    )
    r = run(c, t, FrameTargetBuffers((), (), (), ()))
    assert r.position == c.position
    assert r.rotation == c.rotation  # No quaternion normalization on fallback.
    assert r.scale == c.scale
    assert r.proxy_slots == ()


def test_one_fixed_point_uses_proxy_position_not_component_position():
    r = run()
    assert r.position == (2, 4, 6)
    assert r.scale == (2, 3, 4)
    assert r.proxy_slots == (0,)


def test_identity_point_native_wrapper_swap_adapts_to_up_forward_api():
    r = run()
    assert r.rotation == Q
    assert rotate_single(r.rotation, F) == F
    assert rotate_single(r.rotation, Y) == Y


def test_chunk_start_and_ushort_list_slice_preserve_order_and_duplicates():
    b = buffers(
        fixed_point_data=(999999, 2, 0, 2, 999999),
        proxy_positions=((999, 0, 0), (10, 20, 30), (999, 0, 0), (4, 8, 12)),
        proxy_rotations=(Q,) * 4,
        proxy_bind_rotations=(Q,) * 4,
    )
    r = run(t=team(fixed_point_start=1, fixed_point_count=3, proxy_chunk_start=1), b=b)
    assert r.proxy_slots == (3, 1, 3)
    assert r.position == (6, 12, 18)


def test_double_position_accumulation_order_is_not_sorted_or_compensated():
    b = buffers(
        fixed_point_data=(0, 1, 2),
        proxy_positions=((1e16, 0, 0), (1, 0, 0), (-1e16, 0, 0)),
        proxy_rotations=(Q,) * 3,
        proxy_bind_rotations=(Q,) * 3,
    )
    assert run(t=team(fixed_point_count=3), b=b).position == Z
    reordered = replace(b, fixed_point_data=(0, 2, 1))
    assert run(t=team(fixed_point_count=3), b=reordered).position == (1 / 3, 0, 0)


def test_double_average_preserves_large_world_subsingle_residual():
    b = buffers(
        fixed_point_data=(0, 1),
        proxy_positions=((2**40 + 0.25, 0, 0), (2**40 + 0.75, 0, 0)),
        proxy_rotations=(Q, Q),
        proxy_bind_rotations=(Q, Q),
    )
    assert run(t=team(fixed_point_count=2), b=b).position[0] == 2**40 + 0.5


def test_single_axis_sum_keeps_native_order_and_single_cancellation():
    b = buffers(
        fixed_point_data=(0, 1, 2),
        proxy_positions=(Z,) * 3,
        proxy_rotations=((0.5, 0, 0, 1e8), (0.5, 0, 0, 1), (0.5, 0, 0, -1e8)),
        proxy_bind_rotations=(Q,) * 3,
    )
    r = run(t=team(fixed_point_count=3), b=b)
    assert rotate_single(r.rotation, F) == pytest.approx(F, abs=2e-7)
    reordered = run(
        t=team(fixed_point_count=3), b=replace(b, fixed_point_data=(0, 2, 1))
    )
    assert rotate_single(reordered.rotation, Y) == pytest.approx(
        (0, 1.5 / math.sqrt(3.25), 1 / math.sqrt(3.25)), abs=4e-7
    )


def test_point_rotation_is_left_of_bind_rotation_noncommuting_fixture():
    r = run(b=buffers(proxy_rotations=(X90,), proxy_bind_rotations=(Y90,)))
    # point*bind maps +Y→+Z and +Z→+X. Native ABI adaptation retains these axes.
    # bind*point fails both; a duplicated Y/Z swap fails both too.
    assert rotate_single(r.rotation, F) == pytest.approx((1, 0, 0), abs=6e-7)
    assert rotate_single(r.rotation, Y) == pytest.approx(F, abs=6e-7)


def test_basis_reduction_is_not_quaternion_average():
    b = buffers(
        fixed_point_data=(0, 1),
        proxy_positions=(Z, Z),
        proxy_rotations=(Q, X90),
        proxy_bind_rotations=(Q, Q),
    )
    r = run(t=team(fixed_point_count=2), b=b)
    assert rotate_single(r.rotation, F) == pytest.approx((0, -H, H), abs=4e-7)
    assert rotate_single(r.rotation, Y) == pytest.approx((0, H, H), abs=4e-7)


@pytest.mark.parametrize(
    "seed,negative", [(0, False), (1, False), (2, True), (3, True)]
)
def test_axis_reduction_against_independent_double_rotation_matrices(seed, negative):
    rng = np.random.default_rng(seed)
    point = rng.normal(size=(3, 4))
    point /= np.linalg.norm(point, axis=1)[:, None]
    bind = rng.normal(size=(3, 4))
    bind /= np.linalg.norm(bind, axis=1)[:, None]

    def matrix(q):
        x, y, z, w = q
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )

    negative_reconstruction = np.diag([1, -1, -1])
    rotations = [
        matrix(p) @ (negative_reconstruction if negative else np.eye(3)) @ matrix(b)
        for p, b in zip(point, bind, strict=True)
    ]
    y_sum = sum(m[:, 1] for m in rotations) * (-1 if negative else 1)
    z_sum = sum(m[:, 2] for m in rotations) * (-1 if negative else 1)
    normal = y_sum / np.linalg.norm(y_sum)
    tangent = z_sum / np.linalg.norm(z_sum)
    right = np.cross(normal, tangent)
    right /= np.linalg.norm(right)
    up = np.cross(tangent, right)
    expected = np.column_stack((right, up, tangent))
    b = buffers(
        fixed_point_data=(0, 1, 2),
        proxy_positions=(Z,) * 3,
        proxy_rotations=tuple(tuple(float(v) for v in q) for q in point),
        proxy_bind_rotations=tuple(tuple(float(v) for v in q) for q in bind),
    )
    r = run(
        t=team(
            fixed_point_count=3,
            negative_scale_sign=-1 if negative else 1,
            negative_scale_direction=(-1, 1, 1) if negative else S,
        ),
        b=b,
    )
    actual = np.column_stack([rotate_single(r.rotation, v) for v in ((1, 0, 0), Y, F)])
    np.testing.assert_allclose(actual, expected, atol=2e-6)


def test_nonunit_proxy_rotation_is_not_normalized_before_axis_extraction():
    r = run(b=buffers(proxy_rotations=((0.5, 0, 0, 0.5),)))
    assert rotate_single(r.rotation, F) == pytest.approx((0, -H, H), abs=4e-7)


@pytest.mark.parametrize(
    "direction,expected_forward,expected_up",
    [
        ((-1, 1, 1), F, Y),
        ((1, -1, 1), F, (0, -1, 0)),
        ((1, 1, -1), (0, 0, -1), Y),
        ((-1, -1, 1), F, Y),
        ((-1, -1, -1), F, Y),
        ((0, -1, 1), F, (0, -1, 0)),
    ],
)
def test_negative_point_rebuild_then_postloop_or_signs(
    direction, expected_forward, expected_up
):
    r = run(t=team(negative_scale_sign=-1, negative_scale_direction=direction))
    assert rotate_single(r.rotation, F) == pytest.approx(expected_forward, abs=6e-7)
    assert rotate_single(r.rotation, Y) == pytest.approx(expected_up, abs=6e-7)


def test_positive_sign_does_not_enter_perpoint_rebuild_even_if_direction_negative():
    # Source consumes both distinct caches, not determinant/current scale guessing.
    r = run(t=team(negative_scale_sign=1, negative_scale_direction=(-1, 1, 1)))
    assert rotate_single(r.rotation, F) == pytest.approx((0, 0, -1), abs=3e-7)
    assert rotate_single(r.rotation, Y) == pytest.approx((0, -1, 0), abs=3e-7)


def test_sign_branch_is_strict_less_than_zero_not_negative_flag_or_nonpositive():
    zero = run(t=team(negative_scale_sign=-0.0))
    positive = run(t=team(negative_scale_sign=1))
    assert zero == positive


def test_unused_proxy_slots_and_outside_fixed_slice_are_not_sampled():
    b = buffers(
        fixed_point_data=(999999, 1, 999999),
        proxy_positions=((math.nan,) * 3, (2, 4, 6)),
        proxy_rotations=((math.nan,) * 4, Q),
        proxy_bind_rotations=((math.nan,) * 4, Q),
    )
    assert run(t=team(fixed_point_start=1), b=b).position == (2, 4, 6)


def test_uint16_maximum_is_not_signed_short_or_truncated():
    b = buffers(
        fixed_point_data=(65535,),
        proxy_positions=(Z,) * 65536,
        proxy_rotations=(Q,) * 65536,
        proxy_bind_rotations=(Q,) * 65536,
    )
    assert run(b=b).proxy_slots == (65535,)


def test_resolve_changes_only_frame_target_fields_not_history():
    before = CenterStepState((1, 2, 3), X90, Z, Q, (-3, 4, 5), S, (4, 5, 6), Y90)
    target = run()
    after = resolve_frame_target(before, target)
    assert after.frame_world_position == target.position
    assert after.frame_world_rotation == target.rotation
    assert after.frame_world_scale == target.scale
    assert (
        replace(
            after,
            frame_world_position=before.frame_world_position,
            frame_world_rotation=before.frame_world_rotation,
            frame_world_scale=before.frame_world_scale,
        )
        == before
    )


def test_scale_target_matrix_anchor_prelude_handoff_has_real_produced_target():
    step = CenterStepState((5, 6, 7), Q, Z, Q, S, S, (8, 9, 10), Q)
    s = FrameInertiaState((10, 20, 30), Q, Z, Q, (2, 3, 4), Z, Q, Z, step, (1, 2, 3))
    t = FrameInertiaTeam(0x22, 0.1, 1, 1, 1, 0.02)
    a = AnchorState(Z, Q, Z, Q, Z)
    sign = prepare_component_scale_remap(
        s, t, a, (-2, 3, 4), ComponentScaleCache(Q, S, S)
    )
    target = produce_frame_target(
        ComponentFrameSample(
            s.component_world_position, s.component_world_rotation, (-2, 3, 4)
        ),
        FrameTargetTeam(
            0, 1, 0, sign.signs.negative_scale_sign, sign.signs.negative_scale_direction
        ),
        buffers(),
    )
    resolved = replace(
        sign.state, step_state=resolve_frame_target(sign.state.step_state, target)
    )
    matrices = prepare_frame_scale_matrices(
        resolved.step_state, target.scale, sign.team.flag, IDENTITY
    )
    anchored = advance_frame_anchor(resolved, sign.team, sign.anchor, 1)
    prelude = prepare_frame_inertia(
        anchored.state, anchored.team, FramePreludeSettings(0, -1, 1, 0, 999, 999)
    )
    assert prelude.state.step_state.old_frame_world_position == (2, 4, 6)
    assert prelude.state.step_state.old_frame_world_scale == (-2, 3, 4)
    assert prelude.state.step_state.old_frame_world_rotation == target.rotation
    assert prelude.state.old_component_world_position == (10, 20, 30)
    assert matrices.negative_scale_matrix_updated


@pytest.mark.parametrize("data", [-1, 65536, True, 0.5])
def test_invalid_selected_fixed_point_index_is_adapter_rejection(data):
    with pytest.raises(ValueError):
        run(b=buffers(fixed_point_data=(data,)))


@pytest.mark.parametrize(
    "kw",
    [
        {"fixed_point_start": -1},
        {"fixed_point_count": 2},
        {"proxy_chunk_start": -1},
        {"proxy_chunk_start": 1},
        {"fixed_point_count": True},
        {"fixed_point_count": 2**31},
        {"negative_scale_sign": math.nan},
        {"negative_scale_direction": (1, 2)},
    ],
)
def test_invalid_selected_team_slice_or_cache_is_adapter_rejection(kw):
    with pytest.raises(ValueError):
        run(t=team(**kw))


def test_parallel_global_buffers_required_only_on_selected_fixed_point_path():
    with pytest.raises(ValueError):
        run(b=buffers(proxy_bind_rotations=()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("position", (math.inf, 0, 0)),
        ("rotation", (1, 2, 3)),
        ("scale", (math.nan, 1, 1)),
    ],
)
def test_invalid_component_sample_is_adapter_rejection(field, value):
    with pytest.raises(ValueError):
        run(c=sample(**{field: value}))


def test_selected_invalid_proxy_value_is_adapter_rejection():
    with pytest.raises(ValueError):
        run(b=buffers(proxy_positions=((math.nan, 0, 0),)))


def test_zero_basis_sum_rejected_not_replaced_by_identity_or_safe_lookrotation():
    b = buffers(
        fixed_point_data=(0, 1),
        proxy_positions=(Z, Z),
        proxy_rotations=(Q, (1, 0, 0, 0)),
        proxy_bind_rotations=(Q, Q),
    )
    with pytest.raises(ValueError):
        run(t=team(fixed_point_count=2), b=b)


def test_parallel_up_forward_rejected_not_repaired_by_component_orientation():
    with pytest.raises(ValueError):
        run(b=buffers(proxy_rotations=((0, 0.5, 0.5, 0),)))


def test_double_sum_overflow_is_adapter_rejection():
    b = buffers(fixed_point_data=(0, 0), proxy_positions=((1e308, 0, 0),))
    with pytest.raises(ValueError):
        run(t=team(fixed_point_count=2), b=b)
