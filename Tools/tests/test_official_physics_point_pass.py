"""Analytic serial Point range checks over explicit produced input buffers."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from official_physics_point_collision import (
    ColliderWork,
    PointCollisionParameters,
    PointCollisionState,
)
from official_physics_point_pass import (
    PointPassTeam,
    PointVisit,
    solve_point_collision_range,
    solve_point_collision_slot,
)

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def state(position=(0.0, 0.5, 0.0)):
    return PointCollisionState(
        position, (7.0, 8.0, 9.0), position, 0.0, (9.0, 9.0, 9.0)
    )


def sphere():
    return ColliderWork(
        0x31,
        (-3.0, -3.0, -3.0),
        (3.0, 3.0, 3.0),
        (1.0, 1.0),
        (ZERO, ZERO),
        (ZERO, ZERO),
        IDENTITY,
        IDENTITY,
    )


def fixture():
    sentinel = state((99.0, 98.0, 97.0))
    return {
        "states": (sentinel, sentinel, sentinel, state(), sentinel, state()),
        "teams": {
            1: PointPassTeam(0, 1.0, 6, 2, 1, 1),
            2: PointPassTeam(0, 2.0, 10, 5, 1, 1),
        },
        "parameters": {
            1: PointCollisionParameters(1, (0.25,) * 16, (0.1,) * 16),
            2: PointCollisionParameters(1, (0.25,) * 16, (0.1,) * 16),
        },
        "step_particle_indices": (5, 3),
        "team_ids": (0, 0, 0, 1, 0, 2),
        "attributes": (0,) * 7 + (2,) + (0,) * 2 + (2,),
        "depths": (0.3,) * 11,
        "colliders": (object(), sphere(), object()),
    }


def run(**changes):
    args = fixture()
    args.update(changes)
    return solve_point_collision_range(**args, index_count=2)


def test_ordered_sparse_list_resolves_global_particles_and_distinct_proxy_chunks():
    original = fixture()
    result = solve_point_collision_range(**original, index_count=2)
    assert [
        (v.slot, v.particle_index, v.team_id, v.proxy_index) for v in result.visits
    ] == [
        (0, 5, 2, 10),
        (1, 3, 1, 7),
    ]
    assert result.states[5].next_position == (0.0, 1.5, 0.0)
    assert result.states[3].next_position == (0.0, 1.25, 0.0)
    assert result.states[5].velocity_position == (7.0, 8.0, 9.0)
    assert result.states[3].friction == 1.0
    assert result.visits[1].writes == ("friction", "collision_normal", "next_position")
    assert original["states"][3].next_position == (0.0, 0.5, 0.0)
    assert all(result.states[i] is original["states"][i] for i in (0, 1, 2, 4))


def test_explicit_length_uses_only_prefix_without_reading_tail():
    args = fixture()
    args["step_particle_indices"] = (3, object())
    result = solve_point_collision_range(**args, index_count=1)
    assert len(result.visits) == 1
    assert result.states[5] is args["states"][5]


@pytest.mark.parametrize("length", [0, -1, -2147483648])
def test_nonpositive_signed_length_skips_all_input_resolution(length):
    preserved = state((float("nan"), 0.0, 0.0))
    result = solve_point_collision_range(
        (preserved,),
        {},
        {},
        step_particle_indices=(),
        team_ids=(),
        attributes=(),
        depths=(),
        colliders=(),
        index_count=length,
    )
    assert result.states == (preserved,)
    assert result.visits == ()


def test_zero_team_count_skips_before_parameter_state_and_proxy_reads():
    result = solve_point_collision_range(
        (),
        {1: PointPassTeam(-1, float("nan"), -1, -1, -1, 0)},
        {},
        step_particle_indices=(3,),
        team_ids=(0, 0, 0, 1),
        attributes=(),
        depths=(),
        colliders=(),
        index_count=1,
    )
    visit = result.visits[0]
    assert visit.status == "empty-team-colliders"
    assert visit.proxy_index is None and visit.result is None and visit.writes == ()


@pytest.mark.parametrize("mode", [-2147483648, -1, 0, 2, 2147483647])
def test_other_modes_skip_before_state_attributes_chunks_and_curves(mode):
    result = solve_point_collision_range(
        (),
        {1: PointPassTeam(-1, float("nan"), -1, -1, -1, 1)},
        {1: PointCollisionParameters(mode, (), ())},
        step_particle_indices=(3,),
        team_ids=(0, 0, 0, 1),
        attributes=(),
        depths=(),
        colliders=(),
        index_count=1,
    )
    assert result.visits[0].status == "non-point-mode"
    assert result.visits[0].writes == ()


@pytest.mark.parametrize(
    "attribute,status",
    [
        (0, "invalid-vertex"),
        (0x10, "invalid-vertex"),
        (0x12, "no-collision-vertex"),
        (1, "fixed-ordinary"),
    ],
)
def test_vertex_gates_do_not_read_depth_curves_scale_or_work(attribute, status):
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["attributes"] = (0,) * 7 + (attribute,)
    args["depths"] = ()
    args["colliders"] = ()
    args["teams"][1] = replace(args["teams"][1], scale_ratio=float("nan"))
    args["parameters"][1] = PointCollisionParameters(1, (), ())
    result = solve_point_collision_range(**args, index_count=1)
    assert result.visits[0].status == status
    assert result.states[3] is args["states"][3]
    assert result.visits[0].writes == ()


def test_fixed_spring_and_unrelated_high_flags_are_preserved():
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["attributes"] = (0,) * 7 + (1,)
    args["teams"][1] = replace(args["teams"][1], flag=(1 << 60) | 0x2000)
    result = solve_point_collision_range(**args, index_count=1)
    assert result.visits[0].status == "solved"
    assert result.visits[0].writes[-1] == "velocity_position"
    assert result.states[3].velocity_position[1] > 8.0


def test_team_zero_has_no_added_filter():
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["team_ids"] = (0,) * 6
    args["teams"] = {0: args["teams"][1]}
    args["parameters"] = {0: args["parameters"][1]}
    result = solve_point_collision_range(**args, index_count=1)
    assert result.visits[0].team_id == 0
    assert result.states[3].next_position == (0.0, 1.25, 0.0)


def test_signed_team_id_keeps_sign_in_explicit_map():
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["team_ids"] = (0, 0, 0, -1)
    args["teams"] = {-1: args["teams"][1]}
    args["parameters"] = {-1: args["parameters"][1]}
    result = solve_point_collision_range(**args, index_count=1)
    assert result.visits[0].team_id == -1
    assert result.states[3].next_position == (0.0, 1.25, 0.0)


def test_duplicate_particle_observes_previous_write_and_new_contact_classification():
    args = fixture()
    args["step_particle_indices"] = (3, 3)
    args["states"] = args["states"][:3] + (state(ZERO),) + args["states"][4:]
    plane = replace(sphere(), flag=0x38, old_points=((0.0, 2.0, 0.0), ZERO))
    args["colliders"] = (object(), plane)
    result = solve_point_collision_range(**args, index_count=2)
    first, second = result.visits
    assert first.result is not None and second.result is not None
    assert [first.result.penetrating_contacts, second.result.penetrating_contacts] == [
        1,
        0,
    ]
    assert first.result.state.next_position == (0.0, 2.0, 0.0)
    assert result.states[3].next_position == (0.0, 2.0, 0.0)
    assert result.states[3].collision_normal == ZERO
    assert result.states[3].friction == 1.0
    assert result.visits[1].writes == ("collision_normal", "next_position")


def test_single_slot_does_not_mutate_supplied_states():
    args = fixture()
    visit = solve_point_collision_slot(**args, slot=1)
    assert visit.result is not None
    assert visit.result.state.next_position == (0.0, 1.25, 0.0)
    assert args["states"][3].next_position == (0.0, 0.5, 0.0)


def test_proxy_formula_allows_negative_local_when_final_index_is_valid():
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["teams"][1] = replace(args["teams"][1], proxy_start=9, particle_start=5)
    result = solve_point_collision_range(**args, index_count=1)
    assert result.visits[0].proxy_index == 7


@pytest.mark.parametrize("length", [True, 1.0, 2147483648, -2147483649])
def test_length_requires_exact_signed_int32(length):
    with pytest.raises(ValueError):
        solve_point_collision_range(**fixture(), index_count=length)


def test_length_exceeding_supplied_work_list_is_rejected():
    with pytest.raises(ValueError):
        solve_point_collision_range(**fixture(), index_count=3)


@pytest.mark.parametrize("particle", [-1, True, 1.0, 2147483648, 6])
def test_bad_selected_particle_or_missing_team_id_is_rejected(particle):
    args = fixture()
    args["step_particle_indices"] = (particle,)
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=1)


@pytest.mark.parametrize("team_id", [True, 1.0, -32769, 32768, 3])
def test_team_id_domain_and_required_team_map(team_id):
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["team_ids"] = (0, 0, 0, team_id)
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=1)


def test_nonempty_team_requires_explicit_parameters():
    args = fixture()
    args["parameters"] = {}
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=1)


@pytest.mark.parametrize("proxy_start,particle_start", [(0, 6), (2147483647, 0)])
def test_negative_or_wrapped_negative_proxy_index_is_rejected(
    proxy_start, particle_start
):
    args = fixture()
    args["step_particle_indices"] = (3,)
    args["teams"][1] = replace(
        args["teams"][1], proxy_start=proxy_start, particle_start=particle_start
    )
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=1)


@pytest.mark.parametrize("slot", [-1, True, 1.0, 2])
def test_invalid_slot_is_rejected(slot):
    with pytest.raises(ValueError):
        solve_point_collision_slot(**fixture(), slot=slot)


def test_late_failure_leaves_original_states_unchanged():
    args = fixture()
    args["step_particle_indices"] = (3, 99)
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=2)
    assert args["states"][3].next_position == (0.0, 0.5, 0.0)


def test_missing_internal_write_result_is_rejected_without_input_mutation(monkeypatch):
    import official_physics_point_pass

    args = fixture()
    malformed = PointVisit(0, 3, 1, 7, "solved", None, ("next_position",))
    monkeypatch.setattr(
        official_physics_point_pass,
        "solve_point_collision_slot",
        lambda *a, **k: malformed,
    )
    with pytest.raises(RuntimeError, match="writes without a result"):
        solve_point_collision_range(**args, index_count=1)
    assert args["states"][3].next_position == (0.0, 0.5, 0.0)


@pytest.mark.parametrize("count", [-1, True, 1.0, 2147483648])
def test_invalid_team_collider_count_is_adapter_rejection(count):
    args = fixture()
    args["teams"][2] = replace(args["teams"][2], collider_count=count)
    with pytest.raises(ValueError):
        solve_point_collision_range(**args, index_count=1)
