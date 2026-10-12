"""Selected callback and dependency tests; no native Job/Unity execution."""

import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_animator_dispatch import (
    dispatch_animator_delegate,
    dispatch_animator_read,
    dispatch_animator_write,
)
from official_physics_scheduling import FrameMode

INCOMING = bytes(range(16))
RETURNED = bytes(range(16, 32))
ZERO = bytes(16)
JOB = object()
TRANSFORMS = object()


def helper(kind="delegate", **updates):
    observed = []

    def ordinary(job, dependency):
        observed.append(("ordinary", job, dependency))
        return RETURNED

    def cross(job, dependency):
        observed.append(("cross", job, dependency))
        return RETURNED

    def execute(job):
        observed.append(("execute", job))
        return INCOMING  # Execute return must be ignored.

    args = {
        "mode": FrameMode(True, True),
        "current_thread_id": 23,
        "main_thread_id": 23,
        "job": JOB,
        "dependency": INCOMING,
        "schedule_ordinary": ordinary,
        "schedule_cross_frame": cross,
        "execute": execute,
    } | updates
    call = dispatch_animator_delegate if kind == "delegate" else dispatch_animator_write
    return call(**args), observed


@pytest.mark.parametrize("kind", ["delegate", "write"])
@pytest.mark.parametrize("animator", [False, True])
def test_non_cross_route_uses_ordinary_and_ignores_thread_observations(kind, animator):
    result, observed = helper(
        kind,
        mode=FrameMode(False, animator),
        current_thread_id=cast(Any, object()),
        main_thread_id=None,
        schedule_cross_frame=None,
        execute=None,
    )
    assert result == RETURNED
    assert observed == [("ordinary", JOB, INCOMING)]


@pytest.mark.parametrize("kind", ["delegate", "write"])
def test_cross_main_thread_uses_cross_schedule_with_original_dependency(kind):
    result, observed = helper(kind, schedule_ordinary=None, execute=None)
    assert result == RETURNED
    assert observed == [("cross", JOB, INCOMING)]


@pytest.mark.parametrize("kind", ["delegate", "write"])
def test_cross_animator_worker_executes_directly_and_returns_zero_not_dependency(kind):
    result, observed = helper(
        kind, current_thread_id=-3, schedule_ordinary=None, schedule_cross_frame=None
    )
    assert result == ZERO and result != INCOMING
    assert observed == [("execute", JOB)]  # No implicit Complete callback.


def test_delegate_worker_sync_does_not_require_animator_flag():
    result, observed = helper(mode=FrameMode(True, False), current_thread_id=24)
    assert result == ZERO and observed == [("execute", JOB)]


def test_writer_cross_without_animator_does_not_query_thread_and_remains_scheduled():
    result, observed = helper(
        "write",
        mode=FrameMode(True, False),
        current_thread_id=None,
        main_thread_id=cast(Any, object()),
        execute=None,
    )
    assert result == RETURNED and observed == [("cross", JOB, INCOMING)]


@pytest.mark.parametrize("kind", ["delegate", "write"])
@pytest.mark.parametrize("value", [None, True, 1.0, -(2**31) - 1, 2**31])
@pytest.mark.parametrize("field", ["current_thread_id", "main_thread_id"])
def test_selected_thread_observations_require_signed_int32(kind, value, field):
    with pytest.raises(ValueError, match="thread"):
        helper(kind, **{field: value})


@pytest.mark.parametrize("kind", ["delegate", "write"])
def test_equal_signed_thread_id_limits_are_main_not_worker(kind):
    for value in (-(2**31), 2**31 - 1):
        _, observed = helper(kind, current_thread_id=value, main_thread_id=value)
        assert observed == [("cross", JOB, INCOMING)]


@pytest.mark.parametrize("kind", ["delegate", "write"])
@pytest.mark.parametrize("dependency", [None, b"", bytes(15), bytes(17), bytearray(16)])
def test_dependency_adapter_requires_exact_immutable_16_bytes(kind, dependency):
    with pytest.raises(ValueError, match="16-byte"):
        helper(kind, dependency=dependency)


@pytest.mark.parametrize("kind", ["delegate", "write"])
@pytest.mark.parametrize("route", ["ordinary", "cross", "execute"])
def test_only_selected_callback_is_required(kind, route):
    args: dict[str, Any] = {
        "schedule_ordinary": None,
        "schedule_cross_frame": None,
        "execute": None,
    }
    if route == "ordinary":
        args["mode"] = FrameMode(False, False)
    elif route == "execute":
        args["current_thread_id"] = 24
    with pytest.raises(TypeError, match="callback"):
        helper(kind, **args)


@pytest.mark.parametrize("kind", ["delegate", "write"])
def test_schedule_result_is_validated_not_replaced_by_incoming(kind):
    with pytest.raises(ValueError, match="16-byte"):
        helper(kind, schedule_cross_frame=lambda *args: None)


@pytest.mark.parametrize("kind", ["delegate", "write"])
def test_execute_failure_does_not_return_successful_zero(kind):
    def fail(job):
        raise RuntimeError("selected job failed")

    with pytest.raises(RuntimeError, match="selected job failed"):
        helper(kind, current_thread_id=24, execute=fail)


@pytest.mark.parametrize("count", [-(2**31), -1, 0])
def test_read_nonpositive_count_returns_same_dependency_without_reading_unused_inputs(
    count,
):
    result = dispatch_animator_read(
        transform_count=count,
        job=None,
        transform_access=None,
        dependency=INCOMING,
        schedule_cross_frame_read_only=None,
    )
    assert result is INCOMING


def test_read_positive_count_always_calls_cross_readonly_without_thread_gate():
    observed = []

    def readonly(job, transforms, dependency):
        observed.append((job, transforms, dependency))
        return RETURNED

    result = dispatch_animator_read(
        transform_count=2**31 - 1,
        job=JOB,
        transform_access=TRANSFORMS,
        dependency=INCOMING,
        schedule_cross_frame_read_only=readonly,
    )
    assert result == RETURNED and observed == [(JOB, TRANSFORMS, INCOMING)]


@pytest.mark.parametrize("count", [None, True, 1.0, -(2**31) - 1, 2**31])
def test_read_count_requires_actual_signed_observation(count):
    with pytest.raises(ValueError, match="count"):
        dispatch_animator_read(
            transform_count=count,
            job=JOB,
            transform_access=TRANSFORMS,
            dependency=INCOMING,
            schedule_cross_frame_read_only=None,
        )


def test_read_missing_scheduler_is_not_success_or_direct_execute():
    with pytest.raises(TypeError, match="callback"):
        dispatch_animator_read(
            transform_count=1,
            job=JOB,
            transform_access=TRANSFORMS,
            dependency=INCOMING,
            schedule_cross_frame_read_only=None,
        )


def test_read_invalid_return_does_not_replace_the_handle():
    with pytest.raises(ValueError, match="16-byte"):
        dispatch_animator_read(
            transform_count=1,
            job=JOB,
            transform_access=TRANSFORMS,
            dependency=INCOMING,
            schedule_cross_frame_read_only=lambda *args: bytes(3),
        )


def test_read_to_outer_delegate_threads_actual_backend_handle_without_completing():
    read_handle = dispatch_animator_read(
        transform_count=1,
        job=JOB,
        transform_access=TRANSFORMS,
        dependency=ZERO,
        schedule_cross_frame_read_only=lambda *args: INCOMING,
    )
    result, observed = helper(dependency=read_handle)
    assert observed == [("cross", JOB, INCOMING)] and result == RETURNED


def test_worker_writer_applies_shared_record_and_readback_uses_written_values():
    from official_physics_animator_buffer import read_animator_record_values
    from official_physics_animator_write import (
        AnimatorRecord,
        AnimatorWriteTeam,
        write_animator_buffers,
    )
    from official_physics_publication import TransformBufferSnapshot
    from official_physics_read_restore import ReadRestoreTeam

    q = (0, 0, 0, 1)
    identity = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    record = AnimatorRecord(((1, 2, 3),), (q,), ((4, 5, 6),), (q,), (0,))
    published = []

    def write(job):
        published.append(
            write_animator_buffers(
                flags=(0x14,),
                team_ids=(1,),
                teams=(None, AnimatorWriteTeam(0, 1, 1)),
                buffers=TransformBufferSnapshot(
                    ((0, 0, 0),), (q,), ((8, 9, 10),), (q,)
                ),
                transform_to_handler={0: 0},
                team_to_animator={1: -42},
                animator_records={-42: job},
            )
        )

    result, observed = helper("write", job=record, current_thread_id=24, execute=write)
    assert result == ZERO and not observed and len(published) == 1
    read = read_animator_record_values(
        slot=0,
        transform_valid=True,
        flags=(0x11,),
        team_ids=(1,),
        teams=(None, ReadRestoreTeam(0)),
        transform_to_handler={0: 0},
        team_to_animator={1: -42},
        animator_records=published[0].records,
        native_unit_trs=lambda animator, handler, p, rotation: identity[:3]
        + ((*p, 1),),
    )
    assert read is not None and read.values.local_position == (8, 9, 10)
