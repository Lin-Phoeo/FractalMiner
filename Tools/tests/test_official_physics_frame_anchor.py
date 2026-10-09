"""Finite matrix/anchor fixtures; not native execution or live Unity validation."""

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
from official_physics_frame_inertia import (
    FrameInertiaSettings,
    FrameInertiaState,
    FrameInertiaTeam,
    advance_frame_inertia,
)
from official_physics_frame_prelude import FramePreludeSettings, prepare_frame_inertia
from official_physics_matrix import (
    build_double_trs,
    inverse_double_matrix,
    transform_double_point,
)

Q = (0.0, 0.0, 0.0, 1.0)
Z = (0.0, 0.0, 0.0)
S = (1.0, 1.0, 1.0)
IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def frame(**kw):
    return replace(
        FrameInertiaState(
            (4, 0, 0),
            Q,
            Z,
            Q,
            Z,
            (99, 99, 99),
            Q,
            (99, 99, 99),
            CenterStepState(Z, Q, (4, 0, 0), Q, S, S, Z, Q),
            Z,
        ),
        **kw,
    )


def team(flag=0x8022):
    return FrameInertiaTeam(flag, 1, 1, 0, 1, 0.25)


def anchor(**kw):
    return replace(AnchorState((3, 0, 0), Q, Z, Q, Z), **kw)


def run(s=None, t=None, a=None, inertia=0.5):
    return advance_frame_anchor(s or frame(), t or team(), a or anchor(), inertia)


def test_identity_trs_and_inverse():
    assert build_double_trs(Z, Q, S) == IDENTITY
    assert inverse_double_matrix(IDENTITY) == IDENTITY


def test_trs_columns_scaled_in_double_after_single_rotation_not_single_scaled():
    half = math.sqrt(0.5)
    matrix = build_double_trs(
        (2**40 + 0.25, -2, 3), (0, 0, half, half), (1.1234567, 2, 3)
    )
    assert matrix[3] == (2**40 + 0.25, -2, 3, 1)
    assert matrix[0][1] == float(_single(0.9999999403953552)) * float(
        _single(1.1234567)
    )
    assert matrix[0][1] != _single(matrix[0][1])
    assert matrix[1][0] == -1.9999998807907104


def test_point_adds_column_products_then_translation_in_double_without_w_divide():
    matrix = ((2, 3, 4, 8), (5, 6, 7, 9), (8, 9, 10, 10), (11, 12, 13, 20))
    assert transform_double_point(matrix, (1, 2, 3)) == (47, 54, 61)


def test_point_keeps_left_to_right_rounding():
    m = ((1e16, 0, 0, 0), (-1e16, 1, 0, 0), (1, 0, 1, 0), (1, 0, 0, 1))
    assert transform_double_point(m, (1, 1, 1)) == (2, 1, 1)


def test_inverse_handles_general_non_trs_matrix_not_fastinverse():
    matrix = ((2, 0, 1, 0), (1, 3, 0, 1), (0, 1, 4, 0), (5, 6, 7, 2))
    actual = np.array(inverse_double_matrix(matrix)).T
    expected = np.linalg.inv(np.array(matrix, dtype=float).T)
    np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14)


@pytest.mark.parametrize("seed", range(8))
def test_inverse_general_matrices_against_independent_numpy(seed):
    matrix = np.random.default_rng(seed).normal(size=(4, 4)) + np.eye(4) * 3
    columns = tuple(tuple(float(x) for x in col) for col in matrix.T)
    np.testing.assert_allclose(
        np.array(inverse_double_matrix(columns)).T,
        np.linalg.inv(matrix),
        rtol=2e-14,
        atol=2e-14,
    )


def test_nonunit_quaternion_is_not_normalized_and_full_inverse_roundtrip():
    matrix = build_double_trs((10, -2, 3), (0, 0, 0.5, 0.5), (-2, 3, 4))
    assert matrix[0] == (-1, -1, 0, 0)
    point = transform_double_point(matrix, (1, 2, 3))
    np.testing.assert_allclose(
        transform_double_point(inverse_double_matrix(matrix), point),
        (1, 2, 3),
        atol=1e-14,
    )


@pytest.mark.parametrize("bad", [(), ((1, 2, 3),) * 4, ((math.nan, 0, 0, 0),) * 4])
def test_invalid_matrix_is_adapter_rejection(bad):
    with pytest.raises(ValueError):
        inverse_double_matrix(bad)


def test_singular_inverse_is_adapter_rejection_not_native_nan_policy():
    with pytest.raises(ValueError):
        inverse_double_matrix(((0, 0, 0, 0),) * 4)


def test_transform_validates_position_and_trs_validates_single_scale():
    with pytest.raises(ValueError):
        transform_double_point(IDENTITY, (math.inf, 0, 0))
    with pytest.raises(ValueError):
        build_double_trs(Z, Q, (math.inf, 1, 1))


def test_anchor_shift_rebuilds_world_target_and_weights_separate_offset():
    r = run()
    assert r.state.anchor_shift_vector == (1.5, 0, 0)
    assert r.state.working_old_component_position == (1.5, 0, 0)
    assert r.team.flag == 0x8422
    assert r.state.anchor_shift_rotation == Q
    assert r.anchor.anchor_component_local_position == Z
    assert r.anchor.old_anchor_position == Z
    assert not r.anchor_reinitialized and r.anchor_applied


@pytest.mark.parametrize("inertia,shift", [(0, 3), (1, 0)])
def test_anchor_weight_endpoints_still_set_shift_bit(inertia, shift):
    r = run(inertia=inertia)
    assert r.state.anchor_shift_vector == (shift, 0, 0)
    assert r.team.flag & 0x400


def test_disabled_anchor_zeroes_temporaries_not_work_and_ignores_weight():
    r = run(t=team(0x22), inertia=math.nan)
    assert r.state.anchor_shift_vector == Z and r.state.anchor_shift_rotation == Q
    assert r.state.working_old_component_position == Z
    assert not r.anchor_applied


@pytest.mark.parametrize("bit", [4, 0x10000])
def test_anchor_reset_recomputes_local_position_from_current_not_work(bit):
    r = run(t=team(0x8022 | bit))
    assert r.anchor.old_anchor_position == (3, 0, 0)
    assert r.anchor.old_anchor_rotation == Q
    assert r.anchor.anchor_component_local_position == (1, 0, 0)
    assert r.state.working_old_component_position == (2, 0, 0)
    assert r.anchor_reinitialized


def test_anchor_reset_is_not_conditional_on_anchor_enabled():
    r = run(t=team(0x10022), inertia=math.nan)
    assert r.anchor_reinitialized and not r.anchor_applied
    assert r.anchor.anchor_component_local_position == (1, 0, 0)
    assert r.state.working_old_component_position == Z


def test_rotation_delta_is_current_anchor_times_inverse_old_then_left_multiplied():
    h = math.sqrt(0.5)
    r = run(
        frame(working_old_component_rotation=(h, 0, 0, h)),
        a=anchor(anchor_rotation=(0, 0, h, h)),
        inertia=0,
    )
    np.testing.assert_allclose(
        r.state.working_old_component_rotation, (0.5, 0.5, 0.5, 0.5), atol=2e-7
    )
    np.testing.assert_allclose(r.state.anchor_shift_rotation, (0, 0, h, h), atol=2e-7)


def test_anchor_reconstruction_uses_local_offset_and_not_anchor_position_delta():
    r = run(
        frame(working_old_component_position=(2, 0, 0)),
        a=anchor(anchor_component_local_position=(10, 0, 0)),
    )
    assert r.state.anchor_shift_vector == (5.5, 0, 0)
    assert r.state.working_old_component_position == (7.5, 0, 0)


def test_anchor_world_difference_is_double_then_single_and_shift_back_to_double():
    big = 2**40
    r = run(
        frame(working_old_component_position=(big, 0, 0)),
        a=anchor(anchor_position=(big + 0.5, 0, 0)),
    )
    assert r.state.anchor_shift_vector == (0.25, 0, 0)
    assert r.state.working_old_component_position == (big + 0.25, 0, 0)


def test_anchor_shift_does_not_change_pivot_or_frame_target():
    original = frame(old_component_world_position=(9, 0, 0))
    r = run(original)
    assert r.state.old_component_world_position == original.old_component_world_position
    assert r.state.step_state is original.step_state


def test_rotation_delta_with_nonidentity_old_anchor_has_correct_multiply_order():
    h = math.sqrt(0.5)
    r = run(
        a=anchor(anchor_rotation=(0, 0, h, h), old_anchor_rotation=(h, 0, 0, h)),
        inertia=0,
    )
    np.testing.assert_allclose(
        r.state.anchor_shift_rotation, (-0.5, -0.5, 0.5, 0.5), atol=2e-7
    )


def test_reset_local_position_is_narrowed_after_inverse_transform():
    r = run(frame(component_world_position=(4.123456789, 0, 0)), t=team(0x10022))
    assert r.anchor.anchor_component_local_position == (_single(1.123456789), 0, 0)


def test_active_anchor_local_single_is_widened_for_world_matrix_not_used_as_double():
    r = run(a=anchor(anchor_component_local_position=(0.123456789, 0, 0)), inertia=0)
    assert r.state.anchor_shift_vector == (_single(3 + _single(0.123456789)), 0, 0)


def test_disabled_anchor_leaves_unselected_anchor_fields_unread():
    original = anchor(
        anchor_position=(math.nan, 0, 0), old_anchor_rotation=(0, 0, 0, 0)
    )
    r = run(t=team(0x22), a=original, inertia=math.nan)
    assert r.anchor is original


def test_zero_old_anchor_quaternion_rejected_only_on_active_branch():
    with pytest.raises(ValueError):
        run(a=anchor(old_anchor_rotation=(0, 0, 0, 0)))


def test_anchor_then_smoothing_then_inertia_handoff():
    a = run()
    p = prepare_frame_inertia(
        a.state, a.team, FramePreludeSettings(0.5, -1, 1, 0, 100, 180)
    )
    r = advance_frame_inertia(p.state, p.team, FrameInertiaSettings(1, -1, -1, 1))
    assert p.state.smoothing_velocity == (_single(2.5 * _single(0.13375)), 0, 0)
    assert r.motion.delta_single[0] == p.state.smoothing_velocity[0]
    assert r.component_shift_vector[0] > 3.6
    assert r.step_state.old_frame_world_position == r.component_shift_vector


@pytest.mark.parametrize("bad", [-0.1, 1.1, math.nan])
def test_anchor_inertia_domain_is_adapter_policy(bad):
    with pytest.raises(ValueError):
        run(inertia=bad)
