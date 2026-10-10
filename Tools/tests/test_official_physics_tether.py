"""Independent finite Tether geometry, read gates, indexing and feedback."""

import math
import struct
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_tether import (
    TetherBuffers,
    TetherSettings,
    TetherTeam,
    _clamp01,
    convert_tether_settings,
    solve_tether_range,
    solve_tether_slot,
    tether_particle,
)

ZERO = (0.0, 0.0, 0.0)
POISON = (math.nan, math.nan, math.nan)


@pytest.mark.parametrize(
    "value,expected", [(-1.0, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0)]
)
def test_source_double_clamp_strict_bounds(value, expected):
    assert _clamp01(value) == expected


def test_source_double_clamp_keeps_negative_zero_at_equality():
    assert math.copysign(1, _clamp01(-0.0)) == -1


def single(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def evaluate(
    position,
    *,
    root=ZERO,
    basic=(0, 1, 0),
    root_basic=ZERO,
    velocity=(7, 8, 9),
    compression=0.4,
    stretch=0.03,
):
    return tether_particle(
        position,
        velocity,
        root,
        basic,
        root_basic,
        TetherSettings(compression, stretch),
    )


@pytest.mark.parametrize("cloth_type", [0, 1])
def test_convert_mesh_bone_keeps_serialized_single_and_three_percent_stretch(
    cloth_type,
):
    result = convert_tether_settings(0.4, cloth_type)
    assert result == TetherSettings(single(0.4), single(0.03))


def test_convert_spring_uses_point_eight_without_reading_serialized_value():
    result = convert_tether_settings(math.nan, 10)
    assert result == TetherSettings(single(0.8), single(0.03))


@pytest.mark.parametrize("cloth_type", [-2147483648, -1, 2, 11, 2147483647])
def test_unknown_convert_requires_and_retains_explicit_previous_compression(cloth_type):
    with pytest.raises(ValueError, match="previous"):
        convert_tether_settings(math.nan, cloth_type)
    result = convert_tether_settings(math.nan, cloth_type, previous_compression=-0.0)
    assert math.copysign(1, result.compression_limit) == -1
    assert result.stretch_limit == single(0.03)


@pytest.mark.parametrize("cloth_type", [True, 1.0, 2147483648])
def test_convert_cloth_type_domain_is_explicit_adapter_policy(cloth_type):
    with pytest.raises(ValueError):
        convert_tether_settings(0.4, cloth_type)


@pytest.mark.parametrize("ratio", [0.1, 0.4, 0.59, 1.04, 1.1, 1.5])
def test_axial_soft_compression_and_stretch_not_hard_clamp(ratio):
    lower, upper = single(1 - single(0.4)), single(1 + single(0.03))
    boundary = lower if ratio < lower else upper
    gain = min(1, max(0, abs(ratio - boundary) / single(0.3)))
    # Root-minus-particle direction is -Y; soft correction uses ratio gap.
    correction = -(gain * (ratio - boundary))
    result = evaluate((0, ratio, 0))
    assert result.correction == (0, correction, 0)
    assert result.next_position == (0, ratio + correction, 0)
    assert result.velocity_position == (7, 8 + correction * single(0.7), 9)
    assert result.writes == ("next_position", "velocity_position")
    assert result.status == ("compression" if ratio < lower else "stretch")


@pytest.mark.parametrize(
    "ratio", [single(1 - single(0.4)), 0.9, 1.0, single(1 + single(0.03))]
)
def test_inclusive_dead_band_does_not_read_velocity(ratio):
    result = evaluate((0, ratio, 0), velocity=POISON)
    assert result.writes == () and result.status == "within-limits"
    assert result.velocity_position is POISON


def test_current_length_strict_epsilon_gate_precedes_basic_and_settings_reads():
    result = evaluate(
        (0, single(1e-8) / 2, 0),
        basic=POISON,
        root_basic=POISON,
        velocity=POISON,
        compression=math.nan,
        stretch=math.nan,
    )
    assert result.status == "short-current-edge" and result.writes == ()


def test_current_length_equal_single_epsilon_still_contributes():
    length = single(1e-8)
    result = evaluate((0, length, 0))
    lower = single(1 - single(0.4))
    assert result.status == "compression"
    assert result.next_position == (0, length + (lower - length), 0)


def test_zero_reference_distance_does_not_read_settings_or_velocity():
    result = evaluate(
        (0, 1, 0), basic=ZERO, velocity=POISON, compression=math.nan, stretch=math.nan
    )
    assert result.status == "zero-reference-edge" and result.writes == ()


def test_tiny_nonzero_reference_is_not_treated_as_zero():
    result = evaluate((0, 1, 0), basic=(0, 1e-10, 0))
    assert result.status == "stretch" and result.writes


def test_step_basic_reference_not_static_bind_length_or_origin_distance():
    result = evaluate(
        (0, 2.9, 0), root=(0, 1, 0), basic=(0, 4, 0), root_basic=(0, 1, 0)
    )
    # Current distance1.9 / reference3 is inside the dead band.
    assert result.status == "within-limits"
    assert result.next_position == (0, 2.9, 0)


def test_single_lower_limit_is_not_replaced_with_double_one_minus_compression():
    length = 2.8 - 1
    lower = single(1 - single(0.4))
    ratio = length / 3
    correction = -((lower - ratio) / single(0.3) * (length - lower * 3))
    result = evaluate(
        (0, 2.8, 0), root=(0, 1, 0), basic=(0, 4, 0), root_basic=(0, 1, 0)
    )
    assert result.status == "compression"
    assert result.correction == (0, correction, 0)
    assert lower > ratio > 1 - single(0.4)


def test_nonaxis_component_division_and_double_gap_order():
    p, root = (1.1, 2.2, 3.3), (0.0, 0.0, 0.0)
    vector = tuple(root[i] - p[i] for i in range(3))
    length = math.sqrt(
        (vector[1] * vector[1] + vector[0] * vector[0]) + vector[2] * vector[2]
    )
    boundary = single(1 + single(0.03))
    scalar = min(1, (length - boundary) / single(0.3)) * (length - boundary)
    delta = tuple((v / length) * scalar for v in vector)
    result = evaluate(p)
    assert result.correction == delta
    assert result.next_position == tuple(p[i] + delta[i] for i in range(3))
    assert result.velocity_position == tuple(
        (7, 8, 9)[i] + delta[i] * single(0.7) for i in range(3)
    )


def test_world_origin_retains_double_positions():
    origin = 1e12
    result = evaluate(
        (origin, 2, 0),
        root=(origin, 0, 0),
        basic=(origin, 1, 0),
        root_basic=(origin, 0, 0),
    )
    assert result.next_position == (origin, single(1 + single(0.03)), 0)


def test_finite_parameters_are_not_silently_clamped_to_serialized_domain():
    result = evaluate((0, 0.5, 0), compression=-0.5, stretch=-0.75)
    # Compression is the first branch even when the input bounds cross.
    assert result.status == "compression"
    assert result.next_position == (0, 1.5, 0)


def fixture():
    return {
        "buffers": TetherBuffers(
            (ZERO, (0, 2, 0), ZERO, (99, 99, 99)),
            (ZERO, (7, 8, 9), POISON, POISON),
            (ZERO, (0, 1, 0), ZERO, POISON),
        ),
        "teams": {1: TetherTeam(0, 4)},
        "parameters": {1: TetherSettings(0.4, 0.03)},
        "step_particle_indices": (1,),
        "team_ids": (1, 1, 1, 1),
        "attributes": (0, 0, 0, 0, 1, 2),
        "root_local_indices": (-1, -1, -1, -1, -1, 0),
    }


def test_slot_sparse_proxy_mapping_and_team_local_root():
    args = fixture()
    visit = solve_tether_slot(**args, slot=0)
    assert (
        visit.particle_index,
        visit.team_id,
        visit.proxy_index,
        visit.root_particle_index,
    ) == (1, 1, 5, 0)
    assert visit.result is not None
    assert visit.result.next_position == (0, single(1 + single(0.03)), 0)
    assert args["buffers"].next_positions[1] == (0, 2, 0)


@pytest.mark.parametrize("attribute", [0, 1, 4, 16, 17, 255 & ~2])
def test_only_move_bit_gate_skips_roots_positions_and_velocity(attribute):
    args = fixture()
    args["attributes"] = (0,) * 5 + (attribute,)
    args["root_local_indices"] = ()
    args["buffers"] = TetherBuffers((), (), ())
    visit = solve_tether_slot(**args, slot=0)
    assert visit.status == "non-move" and visit.writes == ()


@pytest.mark.parametrize("attribute", [2, 3, 6, 18, 255])
def test_no_extra_valid_nocollision_or_fixed_spring_gate(attribute):
    args = fixture()
    args["attributes"] = (0,) * 5 + (attribute,)
    assert solve_tether_slot(**args, slot=0).writes == (
        "next_position",
        "velocity_position",
    )


@pytest.mark.parametrize("root", [-1, -2, -2147483648])
def test_any_negative_int32_root_skips_position_buffers(root):
    args = fixture()
    args["root_local_indices"] = (-1,) * 5 + (root,)
    args["buffers"] = TetherBuffers((), (), ())
    visit = solve_tether_slot(**args, slot=0)
    assert visit.status == "no-root" and visit.root_particle_index is None


@pytest.mark.parametrize("team_id", [0, -1, -32768, 32767])
def test_signed_team_identity_is_not_filtered(team_id):
    args = fixture()
    args["team_ids"] = (0, team_id)
    args["teams"] = {team_id: args["teams"][1]}
    args["parameters"] = {team_id: args["parameters"][1]}
    assert solve_tether_slot(**args, slot=0).team_id == team_id


def test_negative_particle_local_offset_can_resolve_valid_proxy():
    args = fixture()
    args["teams"][1] = TetherTeam(2, 6)
    args["buffers"] = replace(
        args["buffers"],
        next_positions=(ZERO, (0, 2, 0), ZERO),
        step_basic_positions=(ZERO, (0, 1, 0), ZERO),
    )
    visit = solve_tether_slot(**args, slot=0)
    assert visit.proxy_index == 5 and visit.root_particle_index == 2


@pytest.mark.parametrize("count", [0, -1, -2147483648])
def test_nonpositive_signed_range_count_reads_no_input(count):
    buffers = TetherBuffers((), (), ())
    result = solve_tether_range(
        buffers,
        {},
        {},
        step_particle_indices=(),
        team_ids=(),
        attributes=(),
        root_local_indices=(),
        index_count=count,
    )
    assert result.buffers is buffers and result.visits == ()


def test_duplicate_work_observes_previous_private_writes_and_velocity_feedback():
    args = fixture()
    args["step_particle_indices"] = (1, 1)
    result = solve_tether_range(**args, index_count=2)
    assert [v.status for v in result.visits] == ["stretch", "within-limits"]
    delta = single(1 + single(0.03)) - 2
    assert result.buffers.velocity_positions[1] == (7, 8 + delta * single(0.7), 9)
    assert args["buffers"].velocity_positions[1] == (7, 8, 9)


def test_updated_root_from_earlier_slot_is_used_not_jacobi_snapshot():
    args = fixture()
    args["buffers"] = TetherBuffers(
        (ZERO, (0, 2, 0), (0, 3, 0)), (ZERO, ZERO, ZERO), (ZERO, (0, 1, 0), (0, 2, 0))
    )
    args["attributes"] = (0,) * 4 + (1, 2, 2)
    args["root_local_indices"] = (-1,) * 4 + (-1, 0, 1)
    args["step_particle_indices"] = (1, 2)
    result = solve_tether_range(**args, index_count=2)
    upper = single(1 + single(0.03))
    assert result.buffers.next_positions == (ZERO, (0, upper, 0), (0, 2 * upper, 0))
    assert all(v.writes for v in result.visits)


@pytest.mark.parametrize("slot", [-1, True, 0.0, 1])
def test_invalid_work_ordinal_is_adapter_error(slot):
    with pytest.raises(ValueError):
        solve_tether_slot(**fixture(), slot=slot)


def test_missing_parameter_and_team_are_adapter_errors():
    args = fixture()
    args["parameters"] = {}
    with pytest.raises(ValueError, match="TeamData.*parameters"):
        solve_tether_slot(**args, slot=0)
    args["teams"] = {}
    with pytest.raises(ValueError):
        solve_tether_slot(**args, slot=0)


@pytest.mark.parametrize(
    "field,value",
    [("team_ids", (0, 32768)), ("root_local_indices", (-1,) * 5 + (2147483648,))],
)
def test_signed_index_source_domains_are_checked(field, value):
    args = fixture()
    args[field] = value
    with pytest.raises(ValueError):
        solve_tether_slot(**args, slot=0)


def test_int32_proxy_wrap_is_not_replaced_by_unbounded_python_arithmetic():
    args = fixture()
    args["teams"][1] = TetherTeam(0, 2147483647)
    with pytest.raises(ValueError):
        solve_tether_slot(**args, slot=0)


def test_slot_current_length_gate_skips_absent_basic_and_velocity_buffers():
    args = fixture()
    args["buffers"] = TetherBuffers((ZERO, (0, single(1e-8) / 2, 0)), (), ())
    visit = solve_tether_slot(**args, slot=0)
    assert visit.status == "short-current-edge" and visit.writes == ()


def test_start_tether_end_following_start_preserves_velocity_reference_effect():
    from official_physics_particle_step import (
        EndStepSettings,
        ParticleEndState,
        finish_particle_step,
    )
    from official_physics_start_step import (
        ParticleStartState,
        ResolvedStartCenter,
        StartStepSettings,
        start_particle_step,
    )

    identity = (0, 0, 0, 1)
    state = ParticleStartState(
        (0, 2, 0), (0, 1, 0), identity, (0, 1, 0), identity, ZERO, 1
    )
    settings = StartStepSettings(
        1, 1, 0.5, (0,) * 16, 1, 1, 1, 0, (0, -1, 0), 1, ZERO, 0
    )
    started = start_particle_step(
        state,
        settings,
        attribute=2,
        center=ResolvedStartCenter(ZERO, ZERO, identity, ZERO, identity),
        wind=ZERO,
    )
    constrained = tether_particle(
        started.next_position,
        started.velocity_position,
        ZERO,
        started.step_basic_position,
        ZERO,
        TetherSettings(0.4, 0.03),
    )
    ended = finish_particle_step(
        ParticleEndState(
            constrained.next_position,
            state.old_position,
            constrained.velocity_position,
            ZERO,
            0,
            0,
            ZERO,
            1,
        ),
        EndStepSettings(0.5, 1, 1, -1, 0, 0, 0),
        attribute=2,
    )
    upper = single(1 + single(0.03))
    correction = upper - 2
    assert ended.old_position == (0, upper, 0)
    assert ended.velocity == (
        0,
        single((upper - (2 + correction * single(0.7))) / 0.5),
        0,
    )
    following = start_particle_step(
        replace(state, old_position=ended.old_position, velocity=ended.velocity),
        settings,
        attribute=2,
        center=ResolvedStartCenter(ZERO, ZERO, identity, ZERO, identity),
        wind=ZERO,
    )
    assert following.velocity_position == (0, single(upper), 0)
    assert following.next_position == (
        0,
        single(upper) + single(ended.velocity[1] * 0.5),
        0,
    )
