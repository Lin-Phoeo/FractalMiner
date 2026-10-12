"""Finite static-source call-order/dependency plans, NOT a Unity Job scheduler.

ClothManager.ClothUpdate369369/0x32ad500: ordinary Transform route, mapping-empty,
stable mode/collections, successful calls and no callback reentrancy. Manager
calls remain OPAQUE: a schedule event is not a completed solve or buffer copy.
Handle labels identify symbolic returned dependencies, not native IDs/liveness.
Completion sites are conditional on the handle's first qword AT THAT SITE.

Cross-frame completion uses ScheduleBatchedCrossFrameJobsAndComplete, not the
ordinary ScheduleBatchedJobsAndComplete. Their internals/handle mutation are
not ported. Hooks and IsPlaying/collection gates are host-side ordering only.
No real arrays, setters, jobs, events or solver are executed. Animator host and
mapping-empty DoAllInOneJob order are finite plans in separate observed phases.
Native delegate scheduling, GCHandle lifetimes and nonempty mapping remain
unported. A plan is not a completed solve or a published runtime buffer.
Validation/count caps are adapter policy, not the game's exceptions/defaults.
"""

from dataclasses import dataclass
from typing import Literal


def _boolean(value: bool) -> None:
    if type(value) is not bool:
        raise ValueError("Adapter requires an explicit boolean")


def _integer(value: int, low: int = 0, high: int = 65536) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Adapter requires a bounded integer")


@dataclass(frozen=True)
class FrameMode:
    cross_frame: bool
    animator_transform: bool

    def __post_init__(self) -> None:
        _boolean(self.cross_frame)
        _boolean(self.animator_transform)


@dataclass(frozen=True)
class ScheduleEvent:
    kind: Literal["host", "schedule", "complete-if-nonzero", "clear-master"]
    call: str
    handle: str | None = None
    depends_on: str | None = None
    step_count: int | None = None
    step_index: int | None = None


@dataclass(frozen=True)
class SchedulePlan:
    events: tuple[ScheduleEvent, ...]
    master_handle: str


@dataclass(frozen=True)
class AnimatorDelegatePlan:
    events: tuple[ScheduleEvent, ...]
    # Diagnostic label for the final call's result. Execute returns void and
    # does not publish this result to ClothManager.masterJob.
    last_call_handle: str
    returns_job_handle: Literal[False] = False


class _Plan:
    def __init__(self) -> None:
        self.events: list[ScheduleEvent] = []
        self.master = "incoming-master"

    def host(self, call: str) -> None:
        self.events.append(ScheduleEvent("host", call))

    def clear(self) -> None:
        self.events.append(ScheduleEvent("clear-master", "ClearMasterJob"))
        self.master = "default"

    def schedule(
        self,
        call: str,
        dependency: str,
        *,
        count: int | None = None,
        index: int | None = None,
    ) -> str:
        handle = f"job:{len(self.events)}"
        self.events.append(
            ScheduleEvent("schedule", call, handle, dependency, count, index)
        )
        return handle

    def chain(
        self, call: str, *, count: int | None = None, index: int | None = None
    ) -> None:
        self.master = self.schedule(call, self.master, count=count, index=index)

    def complete(self, handle: str, *, cross: bool = False) -> None:
        self.events.append(
            ScheduleEvent(
                "complete-if-nonzero",
                "CompleteCrossFrame" if cross else "CompleteOrdinary",
                handle,
            )
        )

    def complete_master(self, mode: FrameMode) -> None:
        self.complete(self.master, cross=mode.cross_frame)
        self.clear()

    def finish(self) -> SchedulePlan:
        return SchedulePlan(tuple(self.events), self.master)


def plan_complete_master(mode: FrameMode) -> SchedulePlan:
    """369360/0x3167490: selected completion-if-job-id-nonzero, then clear 16 bytes."""
    plan = _Plan()
    plan.complete_master(mode)
    return plan.finish()


def plan_early_update(
    mode: FrameMode,
    *,
    process_count: int,
    enabled_team_count: int,
) -> SchedulePlan:
    """369364/0x30c4db0; process dictionary Count, NOT active/enabled team Count.

    Caller supplies counts as observed at source sites. Restore returned job is
    ordinarily completed even with zero enabled teams, if processes exist.
    """
    plan = _Plan()
    _integer(process_count)
    if not process_count or mode.animator_transform:
        return plan.finish()
    _integer(enabled_team_count)
    if mode.cross_frame:
        plan.complete_master(mode)
    if enabled_team_count:
        plan.host("CameraCullingPostProcess")
    restored = plan.schedule("RestoreTransform", "default")
    plan.complete(restored)
    return plan.finish()


def plan_after_update(mode: FrameMode, *, active_team_count: int) -> SchedulePlan:
    """369365/0x3e2caa0: cross+Animator hook ordering only, data update is opaque."""
    plan = _Plan()
    if mode.cross_frame and mode.animator_transform:
        _integer(active_team_count)
        if active_team_count:
            plan.host("CameraCullingPostProcess")
        plan.complete_master(mode)
        plan.host("UpdateTeamAnimatorData")
    return plan.finish()


def should_update_cloth(update_location: int, *, before_late: bool) -> bool:
    """369367/0x3e58db0,369368/0x32ad4b0; metadata enum Before=1, After=0.

    Unknown Int32 values match neither hook; no invented fallback. This does
    not install PlayerLoop hooks or establish the live game's selected mode.
    """
    _integer(update_location, -(2**31), 2**31 - 1)
    _boolean(before_late)
    return update_location == (1 if before_late else 0)


def plan_cloth_update(
    mode: FrameMode,
    *,
    is_playing: bool,
    enabled_team_count: int,
    max_update_count: int,
    mapping_count: int = 0,
    pre_callback: bool = False,
    post_callback: bool = False,
) -> SchedulePlan:
    """Source host order for ordinary and stable cross-frame routes.

    enabled_team_count and max_update_count are observed AFTER AlwaysTeamUpdate,
    mapping_count at the later mapping gate. They are NOT calculated from dt or
    presumed equal to process Count. Negative Int32 step counts skip the source
    loop (jle); finite positive cap 65536 is adapter-only. Aborted gates do not
    read unused counts. Cross+Animator returns after scheduling DoAllInOneJob;
    its mapping gate and re-read of maxUpdateCount belong to the later Execute
    plan, not the host's snapshot. Missing callees stay opaque events.
    """
    _boolean(is_playing)
    _boolean(pre_callback)
    _boolean(post_callback)
    plan = _Plan()
    if not is_playing:
        return plan.finish()
    if pre_callback:
        plan.host("OnPreSimulation")
    plan.host("FrameUpdate")
    if mode.cross_frame:
        plan.complete_master(mode)
    plan.host("AlwaysTeamUpdate")
    _integer(enabled_team_count)
    if not enabled_team_count:
        return plan.finish()  # No post callback, wind or work buffers on this path.
    _integer(max_update_count, -(2**31))
    if not (mode.cross_frame and mode.animator_transform):
        _integer(mapping_count)
        if mapping_count:
            raise NotImplementedError("Nonempty mesh mapping route is not ported")
    plan.host("AlwaysWindUpdate")
    plan.host("WorkBufferUpdate")
    plan.clear()
    if mode.cross_frame and mode.animator_transform:
        plan.host("VirtualMesh.UpdateBuffer")
        plan.chain("ReadAnimatorBufferData")
        for name in (
            "bmHandle",
            "tmHandle",
            "vmHandle",
            "smHandle",
            "wmHandle",
            "meshClothSetHandle",
        ):
            plan.host(f"GCHandle.Alloc.{name}")
        plan.chain("DoAllInOneJob")
        plan.host("CameraCullingPreProcess")
        if post_callback:
            plan.host("OnPostSimulation")
        return plan.finish()
    last_write = "default"
    if mode.cross_frame:
        read = plan.schedule("ReadTransform", "default")
        last_write = plan.schedule("WriteDoubleBufferTransform", read)
        plan.complete(last_write)  # Ordinary completion BEFORE next solve chain.
        plan.chain("ValidPosition")
    else:
        plan.chain("ReadTransform")
    for call in (
        "PreProxyMeshUpdate",
        "CalcCenterAndInertiaAndWind",
        "PreSimulationUpdate",
        "Collider.PreSimulationUpdate",
    ):
        plan.chain(call)
    for index in range(max_update_count):
        plan.chain("SimulationStepUpdate", count=max_update_count, index=index)
    plan.chain("CalcDisplayPosition")
    plan.chain("PostProxyMeshUpdate")
    plan.chain("CopyDoubleBuffer" if mode.cross_frame else "WriteTransform")
    plan.chain("Collider.PostSimulationUpdate")
    plan.chain("PostTeamUpdate")
    plan.host("CameraCullingPreProcess")
    if mode.cross_frame:
        # Source rereads temporary job-id after the earlier completion. We do
        # NOT assume native Complete preserved it or assert a second native call.
        plan.complete(last_write)
    else:
        plan.complete_master(mode)
    if post_callback:
        plan.host("OnPostSimulation")
    return plan.finish()


def plan_animator_delegate(
    *, max_update_count: int, mapping_count: int
) -> AnimatorDelegatePlan:
    """369394/0x5a1b0a8: successful mapping-empty Execute ordering only.

    The caller supplies maxUpdateCount from its read AFTER pre-simulation and
    mappingCount from its later getter. Both observations are required; missing
    mapping state cannot silently become zero. The five GetTarget events precede local
    zero-handle scheduling. wmHandle is resolved but its returned object is
    unused here; the sixth handle is queried only on the unsupported positive
    mapping path. Step count is signed; nonpositive mapping takes the same skip
    branch as zero. Validation limits/atomic rejection are adapter policy.

    Typed live targets, native scheduling, complete/free and actual callbacks
    are not performed by this plan. Each symbol means a callee's returned
    dependency, which may be native default in the worker synchronous route.
    The last PostTeamUpdate return is discarded by Execute; it is not the outer
    deferred job handle or a new ClothManager.masterJob.
    """
    _integer(max_update_count, -(2**31))
    _integer(mapping_count, -(2**31), 2**31 - 1)
    if mapping_count > 0:
        raise NotImplementedError("Nonempty Animator mesh mapping route is not ported")
    plan = _Plan()
    plan.master = "default"  # Execute initializes a local JobHandle, not host master.
    for name in ("bmHandle", "tmHandle", "vmHandle", "smHandle", "wmHandle"):
        plan.host(f"GCHandle.GetTarget.{name}")
    for call in (
        "ValidPosition",
        "PreProxyMeshUpdate",
        "CalcCenterAndInertiaAndWind",
        "PreSimulationUpdate",
        "Collider.PreSimulationUpdate",
    ):
        plan.chain(call)
    for index in range(max_update_count):
        plan.chain("SimulationStepUpdate", count=max_update_count, index=index)
    for call in (
        "CalcDisplayPosition",
        "PostProxyMeshUpdate",
        "WriteAnimatorBufferData",
        "Collider.PostSimulationUpdate",
        "PostTeamUpdate",
    ):
        plan.chain(call)
    return AnimatorDelegatePlan(tuple(plan.events), plan.master)
