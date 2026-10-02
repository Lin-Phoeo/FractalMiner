"""Synthetic baseline wiring tests; not a runtime oracle for native/Burst code."""

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_angle_baseline import (
    AngleSettings,
    BaselineState,
    TeamWindow,
    is_movable,
    resolve_baseline,
    solve_baseline,
    unpack_step_index,
)
from official_physics_angle_cache import (
    EdgeCache,
    initialize_edge_cache,
    limit_cached_edge,
)
from official_physics_angles import restoration_pair

IDENTITY = (0.0, 0.0, 0.0, 1.0)
SENTINEL = EdgeCache((9, 8, 7), IDENTITY, 42, (6, 5, 4))


def fixture(order=(0, 1, 2), attributes=(1, 2, 2)):
    window = TeamWindow(2, 3, 5, 3, 4, 3)
    plan = resolve_baseline(
        1 << 16 | 2,
        [window, window],
        [65535, 65535, 0],
        [65535, 65535, len(order)],
        [65535] * 4 + list(order),
        [999] * 5 + [-1, 0, 1],
        [255] * 5 + list(attributes),
        [0] * 5 + [0, 0.5, 1],
    )
    basic = ((99, 99, 99), (99, 99, 99), (0, 0, 0), (0, 1, 0), (0, 2, 0))
    next_positions = basic[:3] + ((0.8, 0.6, 0), (1.3, 1.4, 0.1))
    state = BaselineState(
        next_positions,
        next_positions,
        basic,
        (IDENTITY,) * 5,
        (0, 0, 0, 0.1, 0.2),
        ((0, 0, 1, 0),) * 5,
        (SENTINEL,) * 5,
    )
    settings = AngleSettings(
        True, True, (20,) * 16, 0.7, (0.16,) * 16, 0.8, 0.5, 0.2, 0.4
    )
    return plan, state, settings


def test_step_packing_zero_extends_signed_int32_and_low16_is_global_baseline():
    assert unpack_step_index(0x8123ABCD) == (0x8123, 0xABCD)
    assert unpack_step_index(0x8123ABCD - 2**32) == (0x8123, 0xABCD)
    assert unpack_step_index(0) == (0, 0)


@pytest.mark.parametrize("bad", [True, 1.0, "1", -(2**31) - 1, 2**32])
def test_bad_packed_word_is_adapter_rejection(bad: Any):
    with pytest.raises(ValueError):
        unpack_step_index(bad)


def test_move_bit_is_mask2_not_fixed_not_invalidmotion_or_other_bits():
    assert [is_movable(a) for a in range(256)] == [bool(a & 2) for a in range(256)]
    # Native IsMove only tests bit1, even if contradictory Fixed bit is also set.
    assert is_movable(3)


@pytest.mark.parametrize("bad", [-1, 256, True, 2.0, "2"])
def test_bad_attribute_is_adapter_rejection(bad: Any):
    with pytest.raises(ValueError):
        is_movable(bad)


def test_three_independent_index_spaces_nonzero_team_windows():
    plan, _, _ = fixture()
    assert (plan.team_index, plan.baseline_index) == (1, 2)
    assert [
        (v.local_index, v.particle_index, v.proxy_index) for v in plan.vertices
    ] == [
        (0, 2, 5),
        (1, 3, 6),
        (2, 4, 7),
    ]
    assert [v.parent_particle_index for v in plan.vertices] == [None, 2, 3]
    assert [v.parent_movable for v in plan.vertices] == [False, False, True]
    assert [v.depth for v in plan.vertices] == [0, 0.5, 1]


def test_preserves_native_uint16_order_and_root_is_slot_not_vertex_zero():
    window = TeamWindow(0, 3, 0, 3, 0, 3)
    plan = resolve_baseline(
        0, [window], [0], [3], [2, 1, 0], [2, 2, -999], [2, 2, 1], [1, 0.5, 0]
    )
    assert [v.local_index for v in plan.vertices] == [2, 1, 0]
    assert plan.vertices[0].parent_particle_index is None
    assert plan.vertices[2].parent_particle_index == 2


def test_empty_baseline_is_valid():
    window = TeamWindow(0, 0, 0, 0, 0, 0)
    plan = resolve_baseline(0, [window], [0], [0], [], [], [], [])
    assert plan.vertices == ()


@pytest.mark.parametrize(
    "which",
    [
        "team",
        "baseline",
        "start",
        "count",
        "chunk",
        "data",
        "local",
        "parent",
        "attribute",
        "depth",
        "window",
    ],
)
def test_index_bounds_and_widths_are_checked_not_python_negative_indexing(which):
    window = TeamWindow(0, 2, 0, 2, 0, 2)
    args: list[Any] = [0, [window], [0], [2], [0, 1], [-1, 0], [1, 2], [0, 1]]
    if which == "team":
        args[0] = 1 << 16
    elif which == "baseline":
        args[0] = 1
    elif which == "start":
        args[2] = [-1]
    elif which == "count":
        args[3] = [65536]
    elif which == "chunk":
        args[2] = [1]
    elif which == "data":
        args[4] = [0]
    elif which == "local":
        args[4] = [0, 2]
    elif which == "parent":
        args[5] = [-1, -1]
    elif which == "attribute":
        args[6] = [1]
    elif which == "depth":
        args[7] = [0, float("nan")]
    elif which == "window":
        args[1] = [replace(window, proxy_start=-1)]
    with pytest.raises(ValueError):
        resolve_baseline(*args)


def test_first_slot_move_rejected_explicitly_not_claimed_native_root_gate():
    with pytest.raises(ValueError, match="first.*movable"):
        fixture(attributes=(2, 2, 2))


def test_cache_prepass_includes_fixed_nonroot_and_copies_root_rotation():
    plan, state, settings = fixture(attributes=(1, 1, 2))
    out = solve_baseline(plan, state, settings)
    assert out.state.rotations[2:4] == (IDENTITY, IDENTITY)
    assert out.state.edge_caches[2] is SENTINEL  # root cache isn't cleared
    assert out.state.edge_caches[3] != SENTINEL  # fixed non-root still initialized
    assert out.state.next_positions[2:4] == state.next_positions[2:4]
    assert [(v.iteration, v.local_index, v.phase) for v in out.visits] == [
        (i, 2, phase) for i in range(3) for phase in ("limit", "restoration")
    ]


def manual_chain(
    plan,
    state,
    settings,
    *,
    snapshot_each_iteration=False,
    reinitialize_each_iteration=False,
    separate_passes=False,
):
    """Integration reference wires already separately tested pair arithmetic."""
    p, velocity, rotations, caches = map(
        list,
        (
            state.next_positions,
            state.velocity_positions,
            state.rotations,
            state.edge_caches,
        ),
    )
    for v in plan.vertices:
        rotations[v.particle_index] = state.basic_rotations[v.particle_index]
        if v.parent_particle_index is not None:
            j, a = v.particle_index, v.parent_particle_index
            caches[j] = initialize_edge_cache(
                state.basic_positions[j],
                state.basic_positions[a],
                p[j],
                p[a],
                state.basic_rotations[a],
                state.basic_rotations[j],
                use_limit=settings.use_limit,
                use_restoration=settings.use_restoration,
            )
    for iteration in range(3):
        frozen_p, frozen_v, frozen_r = p[:], velocity[:], rotations[:]
        phases = ("limit", "restoration") if separate_passes else ("both",)
        for phase in phases:
            for v in plan.vertices:
                if not v.movable:
                    continue
                j, a = v.particle_index, v.parent_particle_index
                assert a is not None
                if reinitialize_each_iteration:
                    caches[j] = initialize_edge_cache(
                        state.basic_positions[j],
                        state.basic_positions[a],
                        p[j],
                        p[a],
                        state.basic_rotations[a],
                        state.basic_rotations[j],
                        use_limit=settings.use_limit,
                        use_restoration=settings.use_restoration,
                    )
                cache = caches[j]
                assert cache is not None and cache.restoration_world_vector is not None
                pp, vv, rr = (
                    (frozen_p, frozen_v, frozen_r)
                    if snapshot_each_iteration
                    else (p, velocity, rotations)
                )
                if settings.use_limit and phase != "restoration":
                    out = limit_cached_edge(
                        pp[j],
                        pp[a],
                        vv[j],
                        vv[a],
                        rr[a],
                        cache,
                        limit_curve=settings.limit_curve,
                        depth=v.depth,
                        limit_stiffness=settings.limit_stiffness,
                        child_friction=state.frictions[j],
                        parent_friction=state.frictions[a],
                        parent_movable=v.parent_movable,
                    )
                    rotations[j] = out.child_rotation
                    pair = out.pair
                    p[j], p[a] = pair.child_position, pair.parent_position
                    velocity[j], velocity[a] = (
                        pair.child_velocity_position,
                        pair.parent_velocity_position,
                    )
                if settings.use_restoration and phase != "limit":
                    pair = restoration_pair(
                        p[j],
                        p[a],
                        velocity[j],
                        velocity[a],
                        cache.restoration_world_vector,
                        converted_stiffness_curve=settings.restoration_curve,
                        depth=v.depth,
                        power_w=settings.power_w,
                        gravity_falloff=settings.gravity_falloff,
                        gravity_dot=settings.gravity_dot,
                        iteration=iteration,
                        child_friction=state.frictions[j],
                        parent_friction=state.frictions[a],
                        parent_movable=v.parent_movable,
                        velocity_attenuation=settings.restoration_attenuation,
                    )
                    p[j], p[a] = pair.child_position, pair.parent_position
                    velocity[j], velocity[a] = (
                        pair.child_velocity_position,
                        pair.parent_velocity_position,
                    )
    return tuple(p), tuple(velocity), tuple(rotations)


def test_three_iterations_in_original_order_read_current_shared_state_not_jacobi():
    plan, state, settings = fixture()
    out = solve_baseline(plan, state, settings)
    expected = manual_chain(plan, state, settings)
    actual = (
        out.state.next_positions,
        out.state.velocity_positions,
        out.state.rotations,
    )
    assert actual == expected
    assert actual != manual_chain(plan, state, settings, snapshot_each_iteration=True)
    assert actual != manual_chain(
        plan, state, settings, reinitialize_each_iteration=True
    )
    assert actual != manual_chain(plan, state, settings, separate_passes=True)
    assert [(v.iteration, v.local_index, v.phase) for v in out.visits] == [
        (i, j, phase)
        for i in range(3)
        for j in (1, 2)
        for phase in ("limit", "restoration")
    ]


@pytest.mark.parametrize(
    "limit,restoration", [(False, False), (True, False), (False, True), (True, True)]
)
def test_switch_combinations_preserve_untouched_cache_lanes_and_inputs(
    limit, restoration
):
    plan, state, settings = fixture()
    original = repr(state)
    settings = replace(settings, use_limit=limit, use_restoration=restoration)
    out = solve_baseline(plan, state, settings)
    assert repr(state) == original
    assert out.state.next_positions[:3] == state.next_positions[:3]
    assert out.state.rotations[:2] == state.rotations[:2]
    assert out.state.edge_caches[:3] == state.edge_caches[:3]
    if not limit and not restoration:
        assert out.state is state and out.visits == ()
    else:
        assert out.state.rotations[2] == IDENTITY
        cache = out.state.edge_caches[3]
        assert cache is not None
        assert cache.local_direction == (
            (0, 1, 0) if limit else SENTINEL.local_direction
        )
        assert cache.restoration_world_vector == (
            (0, 1, 0) if restoration else SENTINEL.restoration_world_vector
        )
        if not limit:
            assert out.state.rotations[2:] == (IDENTITY,) * 3
            assert cache.cached_length == 42


def test_no_existing_cache_still_initializes_selected_lanes_only():
    plan, state, settings = fixture()
    state = replace(state, edge_caches=(None,) * 5)
    out = solve_baseline(plan, state, replace(settings, use_limit=False))
    assert out.state.edge_caches[2] is None
    assert out.state.edge_caches[3] == EdgeCache(None, None, None, (0, 1, 0))


def test_empty_plan_leaves_state_unchanged():
    plan, state, settings = fixture()
    out = solve_baseline(replace(plan, vertices=()), state, settings)
    assert out.state is state and out.visits == ()


@pytest.mark.parametrize("flag", ["use_limit", "use_restoration"])
def test_non_bool_enable_is_adapter_error(flag):
    plan, state, settings = fixture()
    with pytest.raises(ValueError):
        solve_baseline(plan, state, replace(settings, **{flag: 1}))


def test_enabled_state_array_sizes_checked_and_failure_does_not_mutate_inputs():
    plan, state, settings = fixture()
    bad = replace(state, velocity_positions=state.velocity_positions[:-1])
    before = repr(bad)
    with pytest.raises(ValueError):
        solve_baseline(plan, bad, settings)
    assert repr(bad) == before


def test_parent_rotation_outside_baseline_is_caller_cache_not_reset_to_basic():
    plan, state, settings = fixture(order=(0, 2))
    outside_rotation = (0, 0, 1, 0)
    state = replace(
        state, rotations=state.rotations[:3] + (outside_rotation,) + state.rotations[4:]
    )
    out = solve_baseline(plan, state, replace(settings, use_restoration=False))
    reset = replace(
        state, rotations=state.rotations[:3] + (IDENTITY,) + state.rotations[4:]
    )
    assert out.state.rotations[3] == outside_rotation
    assert (
        out.state.next_positions
        != solve_baseline(
            plan, reset, replace(settings, use_restoration=False)
        ).state.next_positions
    )
    # A movable, unlisted parent can receive point corrections, but not a new rotation.
    assert out.state.next_positions[3] != state.next_positions[3]
    assert out.state.edge_caches[3] is SENTINEL
    assert [(v.iteration, v.local_index) for v in out.visits] == [
        (i, 2) for i in range(3)
    ]


def test_reversed_valid_child_order_is_not_silently_topologically_sorted():
    plan, state, settings = fixture(order=(0, 2, 1))
    out = solve_baseline(plan, state, settings)
    other, _, _ = fixture()
    assert (
        out.state.next_positions
        != solve_baseline(other, state, settings).state.next_positions
    )
    assert [v.local_index for v in out.visits[:4]] == [2, 2, 1, 1]


def test_bad_particle_index_refused_before_any_output():
    plan, state, settings = fixture()
    with pytest.raises(ValueError):
        solve_baseline(
            replace(plan, vertices=(replace(plan.vertices[0], particle_index=99),)),
            state,
            settings,
        )


def test_forged_movable_root_plan_rejected_and_original_state_unchanged():
    plan, state, settings = fixture()
    bad = replace(plan, vertices=(replace(plan.vertices[0], movable=True),))
    before = repr(state)
    with pytest.raises(ValueError, match="resolved parent"):
        solve_baseline(bad, state, settings)
    assert repr(state) == before


def test_contradictory_fixed_plus_move_nonroot_is_not_implicitly_pinned():
    plan, state, settings = fixture(attributes=(1, 3, 2))
    out = solve_baseline(plan, state, settings)
    assert out.state.next_positions[3] != state.next_positions[3]
    assert {v.local_index for v in out.visits} == {1, 2}


def test_cache_length_is_taken_once_before_three_passes_not_final_positions():
    plan, state, settings = fixture()
    out = solve_baseline(plan, state, settings)
    expected = initialize_edge_cache(
        state.basic_positions[4],
        state.basic_positions[3],
        state.next_positions[4],
        state.next_positions[3],
        IDENTITY,
        IDENTITY,
        use_limit=True,
        use_restoration=True,
    )
    assert out.state.edge_caches[4] == expected
    assert out.state.next_positions[4] != state.next_positions[4]


def test_repeated_nonroot_data_is_not_deduplicated():
    plan, state, settings = fixture(order=(0, 1, 1))
    out = solve_baseline(plan, state, settings)
    assert len(out.visits) == 12
    assert [v.local_index for v in out.visits] == [1] * 12
