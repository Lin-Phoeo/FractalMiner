"""Source-bound wind membership/ordering tests and finite cross-frame bridge."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_center_step import CenterStepState
from official_physics_constraints import _single
from official_physics_frame_target import (
    ComponentFrameSample,
    FrameTargetBuffers,
    FrameTargetTeam,
    produce_frame_target,
    resolve_frame_target,
)
from official_physics_matrix import transform_double_point
from official_physics_particle_wind import WindForceSettings, particle_wind
from official_physics_scale_remap import prepare_frame_scale_matrices
from official_physics_team_tail import (
    FrameWindState,
    TeamWindState,
    WindInfo,
    WindStepSettings,
    advance_wind_state,
)
from official_physics_wind_zones import (
    WindZoneData,
    produce_frame_local_position,
    select_wind_zones,
)

Z = (0.0, 0.0, 0.0)
Q = (0.0, 0.0, 0.0, 1.0)
I = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)
EPS = _single(1e-6)
MOVING = WindInfo(-1, 12.5, 9, (2, 3, 4))


def zone(**changes):
    return replace(
        WindZoneData(3, 0, (2, 2, 2), 3, 0.4, 10, (0, 0, 2), Z, I, (1.0,) * 16),
        **changes,
    )


def old(zones=()):
    return TeamWindState(tuple(zones), MOVING)


def select(data, **changes):
    args = {"wind_count": len(data), "influence": 1, "frame_world_position": (0, 0, 1)}
    args.update(changes)
    return select_wind_zones(old(), data, **args)


@pytest.mark.parametrize("count", [0, -1, -(2**31)])
def test_no_winds_clears_zones_before_reading_influence_or_position(count):
    previous = old((WindInfo(9, 3, 4, Z),))
    result = select_wind_zones(
        previous,
        (),
        wind_count=count,
        influence=math.nan,
        frame_world_position=(math.nan, math.nan, math.nan),
    )
    assert result.state == TeamWindState((), MOVING)
    assert result.state.moving is MOVING
    assert result.addition_candidates == 0 and result.winner_id == -1


@pytest.mark.parametrize("influence", [0, -1, _single(1e-8)])
def test_frame_influence_gate_clears_zones_but_step_gate_preserves_state(influence):
    previous = old((WindInfo(9, 3, 4, Z),))
    result = select_wind_zones(
        previous,
        (),
        wind_count=100,
        influence=influence,
        frame_world_position=(math.nan, math.nan, math.nan),
    )
    assert result.state == TeamWindState((), MOVING)
    step = advance_wind_state(
        previous,
        WindStepSettings(influence, math.nan, math.nan),
        frame=None,
        scale_ratio=math.nan,
        delta_time=math.nan,
    )
    assert step.state is previous


@pytest.mark.parametrize("flag", [0, 1, 2, 4, 5, 6])
def test_valid_and_enabled_bits_both_required_before_shape_inputs(flag):
    assert (
        select(
            (zone(flag=flag, world_to_local_matrix=(), main=math.nan),),
            frame_world_position=(math.nan,) * 3,
        ).state.zones
        == ()
    )


def test_directional_raw_direction_and_new_clock_not_normalized_or_advanced():
    result = select((zone(size=(math.nan,) * 3, attenuation=(), turbulence=math.nan),))
    assert result.state.zones == (WindInfo(0, -10000.0, 3, (0, 0, 2)),)
    assert result.state.moving is MOVING and result.winner_id == 0


@pytest.mark.parametrize("mode", [0, -1, 3, 9, 11, 2147483647])
def test_other_mode_values_have_no_shape_membership_gate(mode):
    assert len(select((zone(mode=mode, size=(-1, -1, -1)),)).state.zones) == 1


@pytest.mark.parametrize("mode", [1, 10])
@pytest.mark.parametrize("distance,expected", [(2, True), (2.0000003, False)])
def test_sphere_modes_include_exact_radius(mode, distance, expected):
    result = select((zone(mode=mode),), frame_world_position=(0, 0, distance))
    assert bool(result.state.zones) is expected


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("sign", [-1, 1])
def test_box_uses_full_size_and_inclusive_each_axis(axis, sign):
    point = [0.0, 0.0, 0.0]
    point[axis] = sign
    assert (
        len(select((zone(mode=2),), frame_world_position=tuple(point)).state.zones) == 1
    )
    point[axis] = sign * 1.0000002
    assert select((zone(mode=2),), frame_world_position=tuple(point)).state.zones == ()


def test_local_matrix_is_column_major_single_then_double_point_then_single():
    # Double world x retains the .25 that premature float3 narrowing loses.
    matrix = ((1, 0, 0, 0), (0, 2, 0, 0), (0, 0, 3, 0), (-(2**24), -4, -9, 1))
    result = select(
        (zone(mode=1, size=(0.25, 0, 0), world_to_local_matrix=matrix),),
        frame_world_position=(2**24 + 0.25, 2, 3),
    )
    assert len(result.state.zones) == 1
    outside = select(
        (zone(mode=1, size=(0.24, 0, 0), world_to_local_matrix=matrix),),
        frame_world_position=(2**24 + 0.25, 2, 3),
    )
    assert outside.state.zones == ()


def test_float_matrix_is_rounded_before_widening_not_preserved_as_double():
    matrix = (*I[:3], (-16777216.25, 0, 0, 1))
    result = select(
        (zone(mode=1, size=(0.125, 0, 0), world_to_local_matrix=matrix),),
        frame_world_position=(16777216.25, 0, 0),
    )
    assert result.state.zones == ()  # Translation narrows to -16777216.


def test_matrix_point_uses_no_homogeneous_division():
    matrix = (*I[:3], (0, 0, 0, 10))
    assert (
        select(
            (zone(mode=1, size=(0.5, 0, 0), world_to_local_matrix=matrix),)
        ).state.zones
        == ()
    )


def test_later_equal_volume_replaces_earlier_but_larger_does_not():
    result = select((zone(zone_volume=5), zone(zone_volume=5), zone(zone_volume=6)))
    assert tuple(w.wind_id for w in result.state.zones) == (1,)
    assert result.winner_id == 1


def test_max_single_volume_is_included_and_negative_volume_is_not_clamped():
    result = select((zone(zone_volume=3.4028234663852886e38), zone(zone_volume=-1)))
    assert result.winner_id == 1
    assert select((zone(zone_volume=3.4028234663852886e38),)).winner_id == 0


def test_swap_back_removal_moves_last_addition_then_appends_replacement():
    result = select(
        (
            zone(zone_volume=10),
            zone(flag=7),
            zone(flag=7),
            zone(zone_volume=5),
            zone(flag=7),
        )
    )
    assert tuple(w.wind_id for w in result.state.zones) == (2, 1, 3, 4)
    assert result.addition_candidates == 3 and result.winner_id == 3


def test_swap_back_removal_finds_winner_after_preceding_addition():
    result = select(
        (zone(flag=7), zone(zone_volume=10), zone(flag=7), zone(zone_volume=5))
    )
    assert tuple(w.wind_id for w in result.state.zones) == (0, 2, 3)


def test_three_addition_candidates_skip_fourth_before_transform_or_main():
    result = select(
        (
            zone(flag=7),
            zone(flag=7),
            zone(flag=7),
            zone(flag=7, world_to_local_matrix=(), main=math.nan),
        ),
        frame_world_position=(0, 0, 1),
    )
    assert tuple(w.wind_id for w in result.state.zones) == (0, 1, 2)


def test_outside_addition_does_not_consume_candidate_quota():
    result = select(
        (
            zone(flag=7, mode=1, size=(0.1, 0, 0)),
            zone(flag=7),
            zone(flag=7),
            zone(flag=7),
        )
    )
    assert tuple(w.wind_id for w in result.state.zones) == (1, 2, 3)
    assert result.addition_candidates == 3


@pytest.mark.parametrize("main", [0, -1, EPS])
def test_weak_additions_consume_quota_even_when_not_appended(main):
    result = select(
        (
            zone(flag=7, main=main),
            zone(flag=7, main=main),
            zone(flag=7, main=main),
            zone(flag=7),
        )
    )
    assert result.state.zones == () and result.addition_candidates == 3


def test_weak_nonaddition_removes_winner_and_blocks_larger_volume():
    result = select(
        (zone(zone_volume=10), zone(zone_volume=1, main=EPS), zone(zone_volume=2))
    )
    assert result.state.zones == () and result.winner_id == 1


def test_equal_volume_strong_candidate_can_replace_weak_winner():
    result = select((zone(zone_volume=1, main=0), zone(zone_volume=1)))
    assert tuple(w.wind_id for w in result.state.zones) == (1,)


def test_volume_rejected_candidate_skips_direction_main_and_attenuation():
    result = select(
        (
            zone(zone_volume=1),
            zone(
                mode=10,
                zone_volume=2,
                main=math.nan,
                world_position=(math.nan,) * 3,
                attenuation=(),
            ),
        )
    )
    assert result.winner_id == 0


def test_additions_do_not_compete_for_volume_or_read_unused_volume():
    assert select((zone(flag=7, zone_volume=math.nan),)).state.zones[0].wind_id == 0


@pytest.mark.parametrize("distance", [0, EPS])
def test_radial_local_center_skips_direction_curve_and_quota(distance):
    result = select(
        (
            zone(
                flag=7,
                mode=10,
                main=math.nan,
                attenuation=(),
                world_position=(math.nan,) * 3,
            ),
        ),
        frame_world_position=(0, 0, distance),
    )
    assert result.state.zones == () and result.addition_candidates == 0


def test_radial_direction_uses_world_delta_after_single_world_position_widen():
    matrix = ((0, 1, 0, 0), (-1, 0, 0, 0), (0, 0, 1, 0), (-10, -20, -30, 1))
    result = select(
        (
            zone(
                mode=10,
                size=(100, 0, 0),
                world_to_local_matrix=matrix,
                world_position=(10, 20, 30),
                world_wind_direction=(math.nan,) * 3,
            ),
        ),
        frame_world_position=(13, 24, 30),
    )
    assert result.state.zones[0].direction == pytest.approx((0.6, 0.8, 0), abs=1e-7)


def test_radial_large_world_delta_is_narrowed_after_double_subtraction():
    matrix = (*I[:3], (-(2**24), 0, 0, 1))
    result = select(
        (
            zone(
                mode=10,
                size=(2, 0, 0),
                world_to_local_matrix=matrix,
                world_position=(2**24, 0, 0),
            ),
        ),
        frame_world_position=(2**24 + 0.25, 0, 0),
    )
    assert result.state.zones[0].direction == (1, 0, 0)


@pytest.mark.parametrize(
    "sample,expected", [(-1, None), (0, None), (0.25, 0.75), (1, 3), (2, 3)]
)
def test_radial_curve_output_is_clamped_before_main_multiply(sample, expected):
    result = select((zone(mode=10, attenuation=(sample,) * 16),))
    assert (result.state.zones[0].main if result.state.zones else None) == expected


def test_radial_curve_flat_column_order_and_fraction_at_mid_segment():
    samples = (0, 1) + (0,) * 14
    result = select((zone(mode=10, size=(30, 0, 0), attenuation=samples),))
    assert result.state.zones[0].main == pytest.approx(1.5, abs=3e-7)


def test_matching_old_slot_preserves_only_first_matching_clock():
    previous = old((WindInfo(0, 123.5, 99, (8, 8, 8)), WindInfo(0, 77, 5, Z)))
    result = select_wind_zones(
        previous, (zone(),), wind_count=1, influence=1, frame_world_position=(0, 0, 1)
    )
    assert result.state.zones == (WindInfo(0, 123.5, 3, (0, 0, 2)),)
    assert previous.zones[0].main == 99


def test_unselected_old_clock_is_not_read_and_disappeared_zone_gets_new_clock():
    previous = old((WindInfo(9, math.nan, math.nan, (math.nan, math.nan, math.nan)),))
    result = select_wind_zones(
        previous, (zone(),), wind_count=1, influence=1, frame_world_position=(0, 0, 1)
    )
    assert result.state.zones[0].time == -10000


def test_declared_count_ignores_trailing_invalid_table_rows():
    assert len(select((zone(), zone(flag=True)), wind_count=1).state.zones) == 1


def test_frame_local_position_full_inverse_point_keeps_double_residual():
    p = (1e12 + 0.125, -2e12 + 0.25, 3e12 - 0.5)
    component = ComponentFrameSample(p, (0.1, 0.2, 0.3, 0.9), (1.3, -2.7, 0.8))
    target = produce_frame_target(
        component,
        FrameTargetTeam(0, 0, 0, 1, (1, 1, 1)),
        FrameTargetBuffers((), (), (), ()),
    )
    prior = CenterStepState(Z, Q, Z, Q, (1, 1, 1), (1, 1, 1), Z, Q)
    step = resolve_frame_target(prior, target)
    matrices = prepare_frame_scale_matrices(step, target.scale, 0, I)
    local = produce_frame_local_position(step, matrices)
    assert local == tuple(
        _single(v) for v in transform_double_point(matrices.frame_inverse, p)
    )
    assert local != Z  # Native full inverse arithmetic must not be simplified to zero.
    assert step.old_frame_world_position == Z and step.now_world_position == Z


def test_frame_local_position_does_not_rebuild_matrix_or_infer_zero():
    step = CenterStepState(Z, Q, (3, 4, 5), Q, (1, 1, 1), (1, 1, 1), Z, Q)
    matrices = prepare_frame_scale_matrices(step, (1, 1, 1), 0, I)
    matrices = replace(matrices, frame_inverse=I)
    assert produce_frame_local_position(step, matrices) == (3, 4, 5)


def test_two_frames_selection_step_clocks_and_real_particle_wind_bridge():
    data = (
        zone(mode=1, size=(2, 0, 0), world_wind_direction=(0, 0, 1), main=2),
        zone(flag=7, world_wind_direction=(1, 0, 0), main=3),
    )
    previous = old()
    config = WindForceSettings(1, 0, 0, 0, 0, 0.5)
    clocks = []
    forces = []
    for point in ((0, 0, 1), (0, 0, 3)):
        selected = select_wind_zones(
            previous, data, wind_count=2, influence=1, frame_world_position=point
        )
        tail = advance_wind_state(
            selected.state,
            WindStepSettings(1, 1, 0.5),
            frame=FrameWindState(4, (0, 1, 0)),
            scale_ratio=2,
            delta_time=0.5,
        )
        force = particle_wind(
            tail.state,
            config,
            team_id=1,
            root_index=0,
            depth=0.5,
            friction=0,
            zone_turbulence={
                w.wind_id: data[w.wind_id].turbulence for w in tail.state.zones
            },
        )
        forces.append(force.force)
        clocks.append(tuple(w.time for w in tail.state.zones))
        previous = tail.state
    for force, expected in zip(forces, ((3, -1, 2), (3, -1, 0)), strict=True):
        assert force == pytest.approx(expected, abs=3e-7)
    assert clocks[1][0] > clocks[0][1] > -10000
    assert previous.moving.wind_id == MOVING.wind_id


def test_fixed_point_generated_target_not_frame_local_drives_zone_membership():
    target = produce_frame_target(
        ComponentFrameSample((99, 99, 99), Q, (1, 1, 1)),
        FrameTargetTeam(0, 2, 0, 1, (1, 1, 1)),
        FrameTargetBuffers((0, 1), (Z, (2, 0, 0)), (Q, Q), (Q, Q)),
    )
    prior = CenterStepState(Z, Q, Z, Q, (1, 1, 1), (1, 1, 1), Z, Q)
    step = resolve_frame_target(prior, target)
    matrices = prepare_frame_scale_matrices(step, target.scale, 0, I)
    local = produce_frame_local_position(step, matrices)
    matrix = (*I[:3], (-1, 0, 0, 1))
    data = (zone(mode=1, size=(0.5, 0, 0), world_to_local_matrix=matrix),)
    assert select(data, frame_world_position=step.frame_world_position).state.zones
    assert select(data, frame_world_position=local).state.zones == ()
    assert step.old_frame_world_position == Z


def test_main_immediately_above_single_epsilon_is_appended():
    main = _single(EPS * 1.000001)
    assert main > EPS
    assert select((zone(main=main),)).state.zones[0].main == main


def test_weak_candidate_does_not_read_matching_old_clock():
    result = select_wind_zones(
        old((WindInfo(0, math.nan, 1, Z),)),
        (zone(main=0),),
        wind_count=1,
        influence=1,
        frame_world_position=(0, 0, 1),
    )
    assert result.state.zones == ()


def test_radial_zero_attenuation_still_consumes_addition_quota():
    result = select((zone(mode=10, flag=7, attenuation=(0,) * 16),))
    assert result.state.zones == () and result.addition_candidates == 1


@pytest.mark.parametrize("count", [True, 1.5, 2**31, -(2**31) - 1])
def test_adapter_count_requires_int32(count):
    with pytest.raises(ValueError):
        select((zone(),), wind_count=count)


def test_adapter_active_count_cannot_exceed_supplied_table():
    with pytest.raises(ValueError, match="table"):
        select((), wind_count=1)


@pytest.mark.parametrize(
    "changes",
    [
        {"flag": True},
        {"flag": -1},
        {"flag": 2**32},
        {"mode": True},
        {"mode": 2**31},
        {"main": math.nan},
        {"zone_volume": math.inf},
        {"world_to_local_matrix": ()},
        {"world_wind_direction": (math.nan,) * 3},
    ],
)
def test_adapter_invalid_consumed_zone_inputs(changes):
    with pytest.raises(ValueError):
        select((zone(**changes),))


@pytest.mark.parametrize(
    "changes",
    [
        {"attenuation": ()},
        {"world_position": (math.nan,) * 3},
        {"world_position": (0, 0, 1)},
    ],
)
def test_adapter_invalid_consumed_radial_inputs_and_degenerate_world_axis(changes):
    with pytest.raises(ValueError):
        select((zone(mode=10, **changes),))


def test_adapter_invalid_active_frame_or_influence():
    with pytest.raises(ValueError):
        select((zone(),), frame_world_position=(math.nan,) * 3)
    with pytest.raises(ValueError):
        select((zone(),), influence=math.nan)


def test_adapter_matched_clock_must_be_finite():
    with pytest.raises(ValueError):
        select_wind_zones(
            old((WindInfo(0, math.nan, 1, Z),)),
            (zone(),),
            wind_count=1,
            influence=1,
            frame_world_position=(0, 0, 1),
        )
