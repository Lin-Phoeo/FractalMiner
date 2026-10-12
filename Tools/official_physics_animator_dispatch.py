"""Finite Animator scheduling adapters with explicit caller-owned backends.

Read manager 0x5a1c92c -> wrapper0x3b5e68 -> ScheduleCrossFrameReadOnly
0x6985208: count<=0 returns incoming dependency, positive schedules read-only.
DoAllInOneJob Schedule0x5a18270: ordinary when not cross-frame, cross schedule
on main thread, direct Execute+zero on worker (no Animator flag gate here).
Writer Schedule2 0x5a1806c: worker direct route requires cross AND Animator.

No hidden Complete, dependency substitution or GCHandle.Free. Explicit signed
thread observations are compared only on the selected branch. 16-byte values
are opaque handle captures, NOT live native IDs, liveness or completion proof.
Callbacks are invoked by this adapter; native jobs, struct copies, reflection,
TransformAccessArray, allocations/lifetimes and Unity integration are the
backend's responsibility and have not been supplied or verified here. Finite
input/return checks and callback exceptions are adapter policy, not native
fault ordering or race equivalence. Stable successful control paths only.
"""

from collections.abc import Callable
from typing import TypeVar

from official_physics_scheduling import FrameMode

T = TypeVar("T")
DEFAULT_HANDLE = bytes(16)


def _handle(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) != 16:
        raise ValueError("Adapter requires an immutable 16-byte handle capture")
    return value


def _int32(value: int | None, name: str) -> int:
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError(f"Adapter requires signed Int32 {name} observation")
    return value


def _schedule(
    callback: Callable[[T, bytes], bytes] | None, job: T, dependency: bytes
) -> bytes:
    if not callable(callback):
        raise TypeError("Adapter requires selected scheduling callback")
    return _handle(callback(job, dependency))


def _worker(current_thread_id: int | None, main_thread_id: int | None) -> bool:
    return _int32(current_thread_id, "current thread") != _int32(
        main_thread_id, "main thread"
    )


def _execute(callback: Callable[[T], object] | None, job: T) -> bytes:
    if not callable(callback):
        raise TypeError("Adapter requires selected Execute callback")
    callback(job)  # Native Execute returns void; never publish a callback result.
    return DEFAULT_HANDLE


def dispatch_animator_read(
    *,
    transform_count: int,
    job: T,
    transform_access: object,
    dependency: bytes,
    schedule_cross_frame_read_only: Callable[[T, object, bytes], bytes] | None,
) -> bytes:
    """Read manager count gate and dedicated cross-frame Transform scheduler.

    No FrameMode/thread gate is present on this source route. TransformAccess
    and job/native record captures must be prepared by the selected backend.
    """
    dependency = _handle(dependency)
    if _int32(transform_count, "count") <= 0:
        return dependency
    if not callable(schedule_cross_frame_read_only):
        raise TypeError("Adapter requires selected read-only scheduling callback")
    return _handle(schedule_cross_frame_read_only(job, transform_access, dependency))


def dispatch_animator_delegate(
    *,
    mode: FrameMode,
    current_thread_id: int | None,
    main_thread_id: int | None,
    job: T,
    dependency: bytes,
    schedule_ordinary: Callable[[T, bytes], bytes] | None,
    schedule_cross_frame: Callable[[T, bytes], bytes] | None,
    execute: Callable[[T], object] | None,
) -> bytes:
    """DoAllInOneJob-specific Schedule helper, NOT a generic Schedule2 policy."""
    dependency = _handle(dependency)
    if not mode.cross_frame:
        return _schedule(schedule_ordinary, job, dependency)
    if _worker(current_thread_id, main_thread_id):
        return _execute(execute, job)
    return _schedule(schedule_cross_frame, job, dependency)


def dispatch_animator_write(
    *,
    mode: FrameMode,
    current_thread_id: int | None,
    main_thread_id: int | None,
    job: T,
    dependency: bytes,
    schedule_ordinary: Callable[[T, bytes], bytes] | None,
    schedule_cross_frame: Callable[[T, bytes], bytes] | None,
    execute: Callable[[T], object] | None,
) -> bytes:
    """Writer-specific Schedule2: cross non-Animator still schedules on worker.

    Worker Execute ignores the incoming dependency on this particular helper;
    the caller's preconditions/order must establish data readiness. This is NOT
    permission to ignore arbitrary dependencies in a live Unity implementation.
    """
    dependency = _handle(dependency)
    if not mode.cross_frame:
        return _schedule(schedule_ordinary, job, dependency)
    if mode.animator_transform and _worker(current_thread_id, main_thread_id):
        return _execute(execute, job)
    return _schedule(schedule_cross_frame, job, dependency)
