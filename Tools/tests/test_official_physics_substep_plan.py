"""Symbolic host order tests; no native Jobs or collision mathematics execute."""

import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_substep_plan import (
    EMPTY_HANDLE,
    DispatchMode,
    SelfCollisionCounts,
    SubstepInputs,
)
from official_physics_substep_plan import (
    plan_simulation_substep as _plan_simulation_substep,
)

ZERO_COUNTS = SelfCollisionCounts(0, 0, 0, 0)


def plan_simulation_substep(settings, incoming, counts=ZERO_COUNTS):
    """Tests choose an explicitly empty self-collision fixture by default."""
    return _plan_simulation_substep(settings, incoming, counts)


def test_public_api_requires_resolved_self_collision_counts():
    with pytest.raises(TypeError):
        _plan_simulation_substep(inputs(), "in")  # type: ignore[call-arg]


@pytest.mark.parametrize("partial", [(), (0,), (0, 0), (0, 0, 0)])
def test_self_count_constructor_requires_all_four_resolved_counts(partial):
    with pytest.raises(TypeError):
        SelfCollisionCounts(*partial)  # type: ignore[call-arg]


def inputs(**kwargs):
    return replace(SubstepInputs(3, 0, 7, False, False), **kwargs)


def test_normal_host_order_and_both_distance_invocations():
    plan = plan_simulation_substep(inputs(), "incoming")
    assert [call.operation for call in plan.calls] == [
        "SimulationStepTeamUpdateJob",
        "ClearStepCounter",
        "CreateUpdateParticleList",
        "CreateUpdatecolliderListJob",
        "ColliderManager.StartSimulationStep",
        "StartSimulationStepJob",
        "UpdateStepBasicPotureJob",
        "TetherConstraint.SolverConstraint",
        "DistanceConstraint.SolverConstraint",
        "AngleConstraint.SolverConstraint",
        "TriangleBendingConstraint.SolverConstraint",
        "ColliderCollisionConstraint.SolverConstraint",
        "DistanceConstraint.SolverConstraint",
        "MotionConstraint.SolverConstraint",
        "SelfCollisionConstraint.SolverRuntimeSelfCollision",
        "SelfCollisionConstraint.SolveIntersect",
        "EndSimulationStepJob",
        "ColliderManager.EndSimulationStepJob",
    ]
    assert [plan.calls[index].call_site_rva for index in (8, 12)] == [
        0x32B4247,
        0x32B42FB,
    ]


@pytest.mark.parametrize(
    "flags,thread,expected",
    [
        ((False, False), None, DispatchMode.SCHEDULE),
        ((False, True), None, DispatchMode.SCHEDULE),
        ((True, False), None, DispatchMode.CROSS_FRAME_SCHEDULE),
        ((True, True), (20, 20), DispatchMode.CROSS_FRAME_SCHEDULE),
        ((True, True), (21, 20), DispatchMode.INLINE),
    ],
)
def test_eight_inlined_schedule2_routes(flags, thread, expected):
    current, main = thread or (None, None)
    plan = plan_simulation_substep(
        inputs(
            use_cross_frame_job=flags[0],
            use_animator_transform=flags[1],
            current_thread_id=current,
            main_thread_id=main,
        ),
        "incoming",
    )
    jobs = [call for call in plan.calls if call.dispatch != DispatchMode.WRAPPER]
    assert len(jobs) == 8
    assert all(call.dispatch == expected for call in jobs)
    if expected == DispatchMode.INLINE:
        assert all(call.output_handle == EMPTY_HANDLE for call in jobs)
        assert [call.completes_dependency for call in jobs] == [
            True,
            False,
            True,
            True,
            True,
            True,
            True,
            True,
        ]
    else:
        assert not any(call.completes_dependency for call in jobs)


def test_each_call_consumes_previous_return_and_preserves_wrapper_invocations():
    plan = plan_simulation_substep(inputs(), "incoming")
    previous = "incoming"
    for call in plan.calls:
        assert call.input_handle == previous
        previous = call.output_handle
    assert plan.output_handle == previous
    # Missing self primitives are a wrapper no-op, not an omitted caller call.
    assert plan.calls[14].no_op
    assert plan.calls[14].input_handle == plan.calls[14].output_handle
    assert plan.calls[15].no_op


def test_symbol_names_cannot_accidentally_alias_a_return():
    plan = plan_simulation_substep(
        inputs(), "host-return-0/self-broad", SelfCollisionCounts(1, 0, 0, 1)
    )
    for call in plan.calls:
        assert call.input_handle != call.output_handle
    for call in plan.calls[14].nested_calls:
        assert call.input_handle != call.output_handle


@pytest.mark.parametrize("update_count", [-1, 0, 1, 3, 2147483647])
def test_update_count_is_retained_but_does_not_create_host_iterations(update_count):
    plan = plan_simulation_substep(inputs(update_count=update_count), "incoming")
    assert plan.update_count == update_count
    assert len(plan.calls) == 18
    assert plan.calls == plan_simulation_substep(inputs(), "incoming").calls


@pytest.mark.parametrize("update_index", [-2, 0, 1, 9])
def test_self_broad_phase_uses_update_index_not_update_count(update_index):
    plan = plan_simulation_substep(
        inputs(update_count=0, update_index=update_index),
        "incoming",
        SelfCollisionCounts(1, 0, 0, 0),
    )
    call = plan.calls[14]
    assert not call.no_op
    assert call.update_index == update_index
    assert call.nested_calls[0].operation == (
        "SelfCollisionConstraint.SolverBroadPhase"
        if update_index == 0
        else "SelfCollisionConstraint.UpdateBroadPhase"
    )
    assert len(call.nested_calls) == 13
    assert [step.operation for step in call.nested_calls[1:]] == [
        operation
        for _ in range(4)
        for operation in (
            "SolverEdgeEdgeCrossFrameJob",
            "SolverPointTriangleCrossFrameJob",
            "InterlockUtility.SolveAggregateBufferAndClear",
        )
    ]
    assert [step.iteration for step in call.nested_calls[1:]] == [
        iteration for iteration in range(4) for _ in range(3)
    ]
    previous = call.input_handle
    for step in call.nested_calls:
        assert step.input_handle == previous
        previous = step.output_handle
    assert previous == call.output_handle


@pytest.mark.parametrize(
    "counts,active",
    [
        ((0, 0, 0), False),
        ((-1, 0, 0), False),
        ((1, 0, 0), True),
        ((0, 1, 0), True),
        ((0, 0, 1), True),
        ((2147483647, 1, 0), False),
        ((-2147483648, -1, 0), True),
    ],
)
def test_self_primitive_gate_is_signed_int32_sum(counts, active):
    plan = plan_simulation_substep(
        inputs(), "incoming", SelfCollisionCounts(counts[0], counts[1], counts[2], 0)
    )
    assert plan.calls[14].no_op is not active
    assert bool(plan.calls[14].nested_calls) is active


@pytest.mark.parametrize("count,no_op", [(0, True), (1, False), (-1, False)])
def test_intersection_only_zero_is_no_op(count, no_op):
    plan = plan_simulation_substep(
        inputs(), "incoming", SelfCollisionCounts(0, 0, 0, count)
    )
    assert plan.calls[15].no_op is no_op
    assert not plan.calls[15].nested_calls  # Its mathematics remain outside this plan.


def test_step_counter_wraps_and_plan_is_immutable():
    plan = plan_simulation_substep(inputs(simulation_step_count=2147483647), "in")
    assert plan.simulation_step_count == -2147483648
    with pytest.raises(FrozenInstanceError):
        plan.calls = ()  # type: ignore[misc]


@pytest.mark.parametrize("value", [True, 1.0, -2147483649, 2147483648])
@pytest.mark.parametrize(
    "field", ["update_count", "update_index", "simulation_step_count"]
)
def test_invalid_int32_inputs_are_adapter_rejections(value, field):
    with pytest.raises(ValueError):
        plan_simulation_substep(inputs(**{field: value}), "in")


@pytest.mark.parametrize("field", ["use_cross_frame_job", "use_animator_transform"])
def test_dispatch_flags_require_bool(field):
    with pytest.raises(ValueError):
        plan_simulation_substep(inputs(**{field: 1}), "in")


@pytest.mark.parametrize(
    "current,main", [(None, None), (1, None), (None, 1), (True, 1)]
)
def test_thread_id_required_only_for_thread_selecting_branch(current, main):
    with pytest.raises(ValueError):
        plan_simulation_substep(
            inputs(
                use_cross_frame_job=True,
                use_animator_transform=True,
                current_thread_id=current,
                main_thread_id=main,
            ),
            "in",
        )
    # Official short-circuit does not read the thread branch in these settings.
    plan_simulation_substep(
        inputs(current_thread_id=current, main_thread_id=main), "in"
    )


@pytest.mark.parametrize("value", [None, "", 3])
def test_incoming_symbol_requires_nonempty_string(value):
    with pytest.raises(ValueError):
        plan_simulation_substep(inputs(), value)


@pytest.mark.parametrize("field", ["point", "edge", "triangle", "intersect"])
def test_invalid_self_count_is_adapter_rejection(field):
    with pytest.raises(ValueError):
        plan_simulation_substep(inputs(), "in", replace(ZERO_COUNTS, **{field: True}))
