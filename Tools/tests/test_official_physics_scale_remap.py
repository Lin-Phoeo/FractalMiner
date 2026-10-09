"""Finite sign-switch fixtures; no native execution or complete Unity solver claim."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_center_step import CenterStepState
from official_physics_constraints import _single
from official_physics_frame_anchor import AnchorState, advance_frame_anchor
from official_physics_frame_inertia import FrameInertiaState, FrameInertiaTeam
from official_physics_frame_prelude import FramePreludeSettings, prepare_frame_inertia
from official_physics_matrix import build_double_trs, transform_double_point
from official_physics_scale_remap import (
    ComponentScaleCache,
    multiply_double_matrices,
    prepare_component_scale_remap,
    prepare_frame_scale_matrices,
    transform_double_vector,
)

Q = (0.0, 0.0, 0.0, 1.0)
Z = (0.0, 0.0, 0.0)
S = (1.0, 1.0, 1.0)
IDENTITY = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


def state(**kw):
    return replace(
        FrameInertiaState(
            (10, 20, 30),
            Q,
            (99, 99, 99),
            (1, 0, 0, 0),
            (2, 3, 4),
            (7, 8, 9),
            Q,
            (8, 9, 10),
            CenterStepState((5, 6, 7), Q, (11, 21, 31), Q, S, S, (8, 9, 10), Q),
            (1, 2, 3),
        ),
        **kw,
    )


def team(flag=0x22):
    return FrameInertiaTeam(flag, 0.1, 1, 1, 1, 0.02)


def anchor():
    return AnchorState((1, 2, 3), Q, (3, 5, 7), (1, 0, 0, 0), (4, 5, 6))


def run(scale=(-2, 3, 4), cache=None, s=None, t=None):
    return prepare_component_scale_remap(
        s or state(),
        t or team(),
        anchor(),
        scale,
        cache or ComponentScaleCache(Q, S, S),
    )


@pytest.mark.parametrize("seed", range(8))
def test_matrix_product_against_independent_numpy(seed):
    rng = np.random.default_rng(seed)
    a, b = rng.normal(size=(2, 4, 4))
    columns = lambda m: tuple(tuple(float(x) for x in col) for col in m.T)
    actual = np.array(multiply_double_matrices(columns(a), columns(b))).T
    np.testing.assert_allclose(actual, a @ b, rtol=1e-14, atol=1e-14)


def test_matrix_product_retains_double_left_to_right_adds():
    a = ((1e16, 0, 0, 0), (-1e16, 1, 0, 0), (1, 0, 1, 0), (1, 0, 0, 1))
    b = ((1, 1, 1, 1),) * 4
    assert multiply_double_matrices(a, b) == ((2, 1, 1, 1),) * 4


def test_vector_w_is_zero_not_point_and_widening_is_single_then_double():
    m = ((2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (100, 200, 300, 1))
    assert transform_double_vector(m, (1.12345678, 2, 3)) == (
        2 * float(_single(1.12345678)),
        6,
        12,
    )


def test_vector_retains_double_intermediate_until_caller_narrows():
    m = ((1.123456789, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    actual = transform_double_vector(m, (1.12345678, 0, 0))[0]
    assert actual == 1.123456789 * float(_single(1.12345678))
    assert actual != _single(actual)


@pytest.mark.parametrize(
    "scale,sign,triangle",
    [
        ((1, 2, 3), 1, (1, 1)),
        ((-1, 2, 3), -1, (-1, -1)),
        ((1, -2, 3), -1, (1, 1)),
        ((1, 2, -3), -1, (-1, 1)),
        ((-1, -2, 3), -1, (-1, -1)),
        ((-1, -2, -3), -1, (-1, -1)),
    ],
)
def test_any_negative_flag_is_not_determinant_parity(scale, sign, triangle):
    r = run(scale)
    assert r.signs.negative_scale_sign == sign
    assert r.signs.negative_scale_triangle_sign == triangle
    assert bool(r.team.flag & 0x20000) == (sign == -1)


def test_change_cache_is_single_product_of_old_and_new_signs_not_difference():
    r = run((2, -3, 4), ComponentScaleCache(Q, (-1, 1, -1), (-1, 1, -1)))
    assert r.signs.negative_scale_direction == (1, -1, 1)
    assert r.signs.negative_scale_change == (-1, -1, -1)
    assert r.signs.negative_scale_quaternion_value == (-1, 1, -1, 1)


def test_positive_path_clears_negative_flag_and_sets_identity_multiplier():
    r = run(S, t=team(0x20022))
    assert r.team.flag == 0x22
    assert r.signs.negative_scale_quaternion_value == (1, 1, 1, 1)


def test_sign_change_remaps_only_selected_old_fields_before_anchor():
    before = state()
    r = run(s=before)
    # Cnew*inverse(Cold): current root translation plus signed/scaled old-local.
    assert r.state.old_component_world_position == (10, 20, 30)
    assert r.state.working_old_component_position == (10, 20, 30)
    assert r.state.working_old_component_rotation == Q
    assert r.anchor.old_anchor_position == (8, 26, 42)
    assert r.state.smoothing_velocity == (-2, 6, 12)
    assert r.cache.old_component_scale == (-2, 3, 4)
    assert r.cache.old_component_rotation == Q
    assert r.cache.negative_scale_direction == (-1, 1, 1)
    assert r.team.flag == 0x60022
    assert not r.team.flag & 0x400
    assert r.sign_changed
    assert r.component_remap is not None
    assert r.state.step_state == before.step_state  # Not remapped/reset here.
    assert r.state.anchor_shift_vector == before.anchor_shift_vector
    assert r.state.smoothing_shift_vector == before.smoothing_shift_vector
    assert (
        replace(r.anchor, old_anchor_position=anchor().old_anchor_position) == anchor()
    )


def test_same_sign_keeps_old_scale_velocity_and_anchor_but_initializes_working_old():
    cache = ComponentScaleCache((0, 0, 0.5, 0.5), (-4, 2, 3), (-1, 1, 1))
    r = run((-9, 8, 7), cache, t=team(0x40022))
    assert not r.sign_changed and r.component_remap is None
    assert r.cache.old_component_scale == cache.old_component_scale
    assert r.state.working_old_component_position == (2, 3, 4)
    assert r.state.working_old_component_rotation == cache.old_component_rotation
    assert r.state.smoothing_velocity == state().smoothing_velocity
    assert r.anchor == anchor()
    assert r.team.flag == 0x60022  # Existing sign-change flag is NOT cleared here.
    assert r.signs.negative_scale_change == S


def test_unchanged_sign_does_not_inverse_unused_singular_old_scale():
    r = run(S, ComponentScaleCache(Q, Z, S))
    assert not r.sign_changed


def test_zero_and_signed_zero_are_sign_zero_not_negative():
    r = run((0, -0.0, 2))
    assert r.signs.negative_scale_direction == (0, 0, 1)
    assert r.signs.negative_scale_sign == 1
    assert r.sign_changed
    assert r.state.smoothing_velocity == (0, 0, 6)
    assert not r.team.flag & 0x20000


def test_negative_branch_negates_zero_sign_bit_in_quaternion_multiplier():
    r = run((0, -1, 1))
    assert math.copysign(1, r.signs.negative_scale_quaternion_value[0]) == -1
    assert r.signs.negative_scale_quaternion_value == (-0.0, 1, -1, 1)


def test_signed_zero_cache_equality_does_not_trigger_remap_or_inverse():
    r = run((0.0, -0.0, 2), ComponentScaleCache(Q, Z, (-0.0, 0.0, 1)))
    assert not r.sign_changed and r.component_remap is None
    assert not r.team.flag & 0x40000
    assert r.state.old_component_world_position == (2, 3, 4)


def test_nonunit_rotation_and_nonuniform_scale_use_full_inverse():
    cache = ComponentScaleCache((0, 0, 0.5, 0.5), (2, 3, 4), S)
    r = run((-1, 2, 3), cache)
    a = np.array(build_double_trs((10, 20, 30), Q, (-1, 2, 3))).T
    b = np.array(
        build_double_trs(
            (2, 3, 4), cache.old_component_rotation, cache.old_component_scale
        )
    ).T
    expected = a @ np.linalg.inv(b)
    np.testing.assert_allclose(np.array(r.component_remap).T, expected, atol=1e-14)
    assert r.state.working_old_component_rotation == cache.old_component_rotation


def test_large_world_coordinates_are_not_rounded_to_single():
    r = run(s=state(component_world_position=(2**40 + 0.25, 0, 0)))
    assert r.state.old_component_world_position[0] == 2**40 + 0.25
    assert r.anchor.old_anchor_position[0] == 2**40 - 1.75


def test_reset_flag_does_not_skip_the_earlier_sign_remap():
    r = run(t=team(4))
    assert r.sign_changed and r.team.flag == 0x60004


def test_frame_inverse_is_produced_even_when_sign_matrix_is_not_updated():
    step = state().step_state
    r = prepare_frame_scale_matrices(step, (-2, 3, 4), 0, IDENTITY)
    assert not r.negative_scale_matrix_updated
    assert r.negative_scale_matrix == IDENTITY
    p = transform_double_point(r.frame_inverse, step.frame_world_position)
    assert p == pytest.approx(Z, abs=1e-14)


def test_frame_matrix_uses_old_frame_fields_not_component_or_now_world():
    step = replace(
        state().step_state,
        old_frame_world_scale=(2, 3, 4),
        now_world_position=(999, 999, 999),
    )
    r = prepare_frame_scale_matrices(step, (-2, 3, 4), 0x40000, IDENTITY)
    assert r.negative_scale_matrix_updated
    assert transform_double_point(r.negative_scale_matrix, (6, 8, 10)) == (10, 23, 34)
    assert transform_double_point(r.negative_scale_matrix, (5, 6, 7)) == (11, 21, 31)
    assert step.old_frame_world_position == (5, 6, 7)


def test_frame_matrix_uses_component_scale_not_stale_frame_scale():
    step = replace(state().step_state, frame_world_scale=(99, 99, 99))
    r = prepare_frame_scale_matrices(step, (-2, 3, 4), 0x40000, IDENTITY)
    assert r.negative_scale_matrix[0] == (-2, 0, 0, 0)


def test_frame_matrix_distinct_rotations_against_independent_numpy():
    step = replace(
        state().step_state,
        old_frame_world_rotation=(0.3, 0, 0, 0.7),  # Nonunit, no normalize shortcut.
        frame_world_rotation=(0, 0.6, 0, 0.8),
        now_world_rotation=(0, 0, 1, 0),
        old_frame_world_scale=(2, 3, 4),
    )
    current = np.array(
        build_double_trs(
            step.frame_world_position, step.frame_world_rotation, (-2, 4, 3)
        )
    ).T
    old = np.array(
        build_double_trs(
            step.old_frame_world_position,
            step.old_frame_world_rotation,
            step.old_frame_world_scale,
        )
    ).T
    r = prepare_frame_scale_matrices(step, (-2, 4, 3), 0x40000, IDENTITY)
    np.testing.assert_allclose(
        np.array(r.frame_inverse).T, np.linalg.inv(current), atol=2e-13
    )
    np.testing.assert_allclose(
        np.array(r.negative_scale_matrix).T, current @ np.linalg.inv(old), atol=2e-13
    )


def test_non_switch_frame_does_not_inverse_old_frame_singular_scale():
    step = replace(state().step_state, old_frame_world_scale=Z)
    assert not prepare_frame_scale_matrices(
        step, S, 0, IDENTITY
    ).negative_scale_matrix_updated


def test_scale_to_anchor_to_prelude_resets_history_only_at_prelude_boundary():
    r = run()
    # Caller center publication (not implemented here) supplies the same frame's
    # current component scale, before anchor/prelude consumption.
    resolved = replace(
        r.state, step_state=replace(r.state.step_state, frame_world_scale=(-2, 3, 4))
    )
    matrices = prepare_frame_scale_matrices(
        resolved.step_state, (-2, 3, 4), r.team.flag, IDENTITY
    )
    a = advance_frame_anchor(resolved, r.team, r.anchor, 1)
    assert a.state.step_state.old_frame_world_position == (5, 6, 7)
    p = prepare_frame_inertia(
        a.state, a.team, FramePreludeSettings(0, -1, 1, 0, 999, 999)
    )
    assert p.history_reinitialized
    assert p.state.step_state.old_frame_world_position == (11, 21, 31)
    assert p.state.step_state.old_frame_world_scale == (-2, 3, 4)
    assert p.state.old_component_world_position == (10, 20, 30)
    assert transform_double_point(
        matrices.negative_scale_matrix, (5, 6, 7)
    ) == pytest.approx((11, 21, 31))


@pytest.mark.parametrize("bad", [(), ((1, 2, 3),) * 4, ((math.nan, 0, 0, 0),) * 4])
def test_invalid_matrix_is_finite_adapter_rejection(bad):
    with pytest.raises(ValueError):
        multiply_double_matrices(bad, IDENTITY)
    with pytest.raises(ValueError):
        transform_double_vector(bad, S)


@pytest.mark.parametrize("bad", [(math.inf, 1, 1), (1, 2)])
def test_invalid_single_scale_is_adapter_rejection(bad):
    with pytest.raises(ValueError):
        run(bad)


def test_singular_selected_inverse_is_adapter_rejection_not_native_policy():
    with pytest.raises(ValueError):
        run((-1, 1, 1), ComponentScaleCache(Q, Z, S))
    with pytest.raises(ValueError):
        prepare_frame_scale_matrices(state().step_state, Z, 0, IDENTITY)
    with pytest.raises(ValueError):
        prepare_frame_scale_matrices(
            replace(state().step_state, old_frame_world_scale=Z), S, 0x40000, IDENTITY
        )


def test_invalid_flag_and_overflow_are_adapter_rejection():
    with pytest.raises(ValueError):
        run(t=team(-1))
    with pytest.raises(ValueError):
        prepare_frame_scale_matrices(state().step_state, S, -1, IDENTITY)
    m = ((1e308, 0, 0, 0),) * 4
    with pytest.raises(ValueError):
        multiply_double_matrices(m, ((2, 2, 2, 2),) * 4)
