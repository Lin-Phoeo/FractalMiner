"""Symbolic normal host dependency plan for SimulationStepUpdate (370401).

The 18 caller stages and returned-handle dependencies are source-backed. Eight
inlined Schedule2 choices are resolved from explicit flags/thread IDs. Wrapper
results remain opaque symbols; self-collision's observed gate and four rounds
are described, not executed. No native Jobs, Burst, arrays, bones or solver math
are run. This is NOT a complete scheduler or an execution/parity oracle.
Null/class-init/fault paths and runtime flag changes between calls are excluded.
Strict types/ranges/symbol checks are adapter policy, not native validation.
"""

from dataclasses import dataclass
from enum import Enum

EMPTY_HANDLE = "<empty-job-handle>"


class DispatchMode(str, Enum):
    SCHEDULE = "schedule"
    CROSS_FRAME_SCHEDULE = "cross_frame_schedule"
    INLINE = "inline"
    WRAPPER = "wrapper-unresolved"


@dataclass(frozen=True)
class SubstepInputs:
    update_count: int
    update_index: int
    simulation_step_count: int
    use_cross_frame_job: bool
    use_animator_transform: bool
    current_thread_id: int | None = None
    main_thread_id: int | None = None


@dataclass(frozen=True)
class SelfCollisionCounts:
    point: int
    edge: int
    triangle: int
    intersect: int


@dataclass(frozen=True)
class PlannedCall:
    operation: str
    input_handle: str
    output_handle: str
    call_site_rva: int
    dispatch: DispatchMode
    completes_dependency: bool = False
    no_op: bool = False
    update_index: int | None = None
    iteration: int | None = None
    nested_calls: tuple["PlannedCall", ...] = ()


@dataclass(frozen=True)
class SubstepPlan:
    update_count: int  # This manager method does not consume or loop over it.
    update_index: int
    simulation_step_count: int  # Incremented once at 0x32b2fe6.
    calls: tuple[PlannedCall, ...]
    output_handle: str


def _int32(value: object) -> int:
    if type(value) is not int or not -0x80000000 <= value <= 0x7FFFFFFF:
        raise ValueError("Adapter requires a signed Int32")
    return value


def _wrap32(value: int) -> int:
    return ((value + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def _dispatch(inputs: SubstepInputs) -> DispatchMode:
    if (
        type(inputs.use_cross_frame_job) is not bool
        or type(inputs.use_animator_transform) is not bool
    ):
        raise ValueError("Adapter requires strict boolean dispatch flags")
    if not inputs.use_cross_frame_job:
        return DispatchMode.SCHEDULE
    if inputs.use_animator_transform:
        current = _int32(inputs.current_thread_id)
        main = _int32(inputs.main_thread_id)
        if current != main:
            return DispatchMode.INLINE
    return DispatchMode.CROSS_FRAME_SCHEDULE


# (operation, normal cross-frame indirect site, ordinary site, inline site).
# Generic method identity resolves each job type, NOT a live reflected pointer.
_JOBS = (
    ("SimulationStepTeamUpdateJob", 0x32B3203, 0x4D58CBC, 0x4D58D19),
    ("ClearStepCounter", 0x32B3492, 0x4D58DE1, 0x4D58E2D),
    ("CreateUpdateParticleList", 0x32B384F, 0x4D58F2B, 0x4D58F85),
    ("CreateUpdatecolliderListJob", 0x32B3A4B, 0x4D59033, 0x4D5908B),
    ("StartSimulationStepJob", 0x32B3EB2, 0x4D5916E, 0x4D591C8),
    ("UpdateStepBasicPotureJob", 0x32B41ED, 0x4D592C9, 0x4D59323),
    ("EndSimulationStepJob", 0x32B46C7, 0x4D59403, 0x4D5945D),
    ("ColliderManager.EndSimulationStepJob", 0x32B48BB, 0x4D59519, 0x4D59570),
)
_CONSTRAINTS = (
    ("TetherConstraint.SolverConstraint", 0x32B421A),
    ("DistanceConstraint.SolverConstraint", 0x32B4247),
    ("AngleConstraint.SolverConstraint", 0x32B4274),
    ("TriangleBendingConstraint.SolverConstraint", 0x32B42A1),
    ("ColliderCollisionConstraint.SolverConstraint", 0x32B42CE),
    ("DistanceConstraint.SolverConstraint", 0x32B42FB),
    ("MotionConstraint.SolverConstraint", 0x32B4328),
)


def _self_calls(incoming: str, update_index: int) -> tuple[PlannedCall, ...]:
    broad = (
        ("SelfCollisionConstraint.SolverBroadPhase", 0x4B2864E)
        if update_index == 0
        else ("SelfCollisionConstraint.UpdateBroadPhase", 0x4B28647)
    )
    result = [
        PlannedCall(
            broad[0], incoming, f"{incoming}/self-broad", broad[1], DispatchMode.WRAPPER
        )
    ]
    for iteration in range(4):
        for part, (operation, site) in enumerate(
            (
                ("SolverEdgeEdgeCrossFrameJob", 0x4B286FF),
                ("SolverPointTriangleCrossFrameJob", 0x4B28772),
                ("InterlockUtility.SolveAggregateBufferAndClear", 0x4B2879A),
            )
        ):
            result.append(
                PlannedCall(
                    operation,
                    result[-1].output_handle,
                    f"{incoming}/self-round-{iteration}-{part}",
                    site,
                    DispatchMode.WRAPPER,
                    iteration=iteration,
                )
            )
    return tuple(result)


def plan_simulation_substep(
    inputs: SubstepInputs,
    incoming_handle: str,
    self_counts: SelfCollisionCounts,
) -> SubstepPlan:
    """Describe one successful host invocation with stable resolved flags.

    All self primitive/intersection counts must be supplied explicitly; missing
    native state is not silently replaced by zero. A symbol denotes an opaque
    returned handle and may alias earlier handles at
    runtime. Only the two proved self-collision no-op paths retain the incoming
    symbol explicitly. ClearStepCounter's special inline branch omits Complete;
    each of the other seven inline jobs completes its dependency first. Wrapper
    internals, counts/reflection pointers, native concurrency and execution order
    within any scheduled range are deliberately unresolved.
    """
    update_count = _int32(inputs.update_count)
    update_index = _int32(inputs.update_index)
    step_count = _wrap32(_int32(inputs.simulation_step_count) + 1)
    counts = tuple(
        _int32(value)
        for value in (
            self_counts.point,
            self_counts.edge,
            self_counts.triangle,
            self_counts.intersect,
        )
    )
    if type(incoming_handle) is not str or not incoming_handle:
        raise ValueError("Adapter requires a nonempty incoming handle symbol")
    dispatch = _dispatch(inputs)
    calls: list[PlannedCall] = []

    def append(
        operation: str,
        site: int,
        mode: DispatchMode = DispatchMode.WRAPPER,
        *,
        no_op: bool = False,
        nested: tuple[PlannedCall, ...] = (),
        index: int | None = None,
    ) -> None:
        incoming = calls[-1].output_handle if calls else incoming_handle
        output = (
            incoming
            if no_op
            else nested[-1].output_handle
            if nested
            else EMPTY_HANDLE
            if mode == DispatchMode.INLINE
            else f"{incoming_handle}/host-return-{len(calls)}"
        )
        calls.append(
            PlannedCall(
                operation,
                incoming,
                output,
                site,
                mode,
                mode == DispatchMode.INLINE and operation != "ClearStepCounter",
                no_op,
                index,
                nested_calls=nested,
            )
        )

    def job(number: int) -> None:
        operation, cross, ordinary, inline = _JOBS[number]
        site = (
            ordinary
            if dispatch == DispatchMode.SCHEDULE
            else inline
            if dispatch == DispatchMode.INLINE
            else cross
        )
        append(
            operation,
            site,
            dispatch,
            index=update_index if number in (0, 3) else None,
        )

    for number in range(4):
        job(number)
    append("ColliderManager.StartSimulationStep", 0x32B3A7B)
    job(4)
    job(5)
    for operation, site in _CONSTRAINTS:
        append(operation, site)
    active_self = _wrap32(counts[0] + counts[1] + counts[2]) > 0
    nested = _self_calls(calls[-1].output_handle, update_index) if active_self else ()
    append(
        "SelfCollisionConstraint.SolverRuntimeSelfCollision",
        0x32B4361,
        no_op=not active_self,
        nested=nested,
        index=update_index,
    )
    append(
        "SelfCollisionConstraint.SolveIntersect",
        0x32B437E,
        no_op=counts[3] == 0,
    )
    job(6)
    job(7)
    return SubstepPlan(
        update_count, update_index, step_count, tuple(calls), calls[-1].output_handle
    )
