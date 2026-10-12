"""Source ordering across Animator host, delegate and post-update boundaries."""

import sys
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_scheduling import (
    FrameMode,
    plan_after_update,
    plan_animator_delegate,
    plan_cloth_update,
)


def calls(plan):
    return [event.call for event in plan.events]


PREFIX = [
    "GCHandle.GetTarget.bmHandle",
    "GCHandle.GetTarget.tmHandle",
    "GCHandle.GetTarget.vmHandle",
    "GCHandle.GetTarget.smHandle",
    "GCHandle.GetTarget.wmHandle",
    "ValidPosition",
    "PreProxyMeshUpdate",
    "CalcCenterAndInertiaAndWind",
    "PreSimulationUpdate",
    "Collider.PreSimulationUpdate",
]
TAIL = [
    "CalcDisplayPosition",
    "PostProxyMeshUpdate",
    "WriteAnimatorBufferData",
    "Collider.PostSimulationUpdate",
    "PostTeamUpdate",
]


def test_missing_mapping_observation_cannot_be_replaced_by_default_zero():
    with pytest.raises(TypeError, match="mapping_count"):
        cast(Any, plan_animator_delegate)(max_update_count=0)


def test_delegate_uses_animator_writer_after_display_and_proxy_without_last_copy():
    plan = plan_animator_delegate(max_update_count=2, mapping_count=0)
    assert calls(plan) == PREFIX + ["SimulationStepUpdate"] * 2 + TAIL
    assert "CopyDoubleBuffer" not in calls(plan)
    assert "WriteTransform" not in calls(plan)
    assert "CameraCullingPreProcess" not in calls(plan)
    assert "UpdateTeamAnimatorData" not in calls(plan)
    assert "GCHandle.Free" not in calls(plan)
    assert plan.returns_job_handle is False  # Native Execute returns void.


def test_delegate_threads_each_returned_dependency_without_publishing_host_master():
    plan = plan_animator_delegate(max_update_count=3, mapping_count=0)
    jobs = [event for event in plan.events if event.kind == "schedule"]
    assert jobs[0].depends_on == "default"  # Local zero handle in Execute.
    for before, after in pairwise(jobs):
        assert after.depends_on == before.handle
    assert plan.last_call_handle == jobs[-1].handle
    assert jobs[-1].call == "PostTeamUpdate"


@pytest.mark.parametrize("count", [-(2**31), -1, 0, 1, 4])
def test_delegate_signed_count_controls_zero_based_steps_at_execute_read_site(count):
    plan = plan_animator_delegate(max_update_count=count, mapping_count=0)
    steps = [e for e in plan.events if e.call == "SimulationStepUpdate"]
    assert [(e.step_count, e.step_index) for e in steps] == [
        (count, i) for i in range(max(0, count))
    ]
    assert calls(plan)[-5:] == TAIL


@pytest.mark.parametrize("count", [0, -1, -(2**31)])
def test_nonpositive_mapping_count_does_not_resolve_sixth_handle(count):
    assert (
        calls(plan_animator_delegate(max_update_count=0, mapping_count=count))
        == PREFIX + TAIL
    )


def test_nonempty_mesh_mapping_is_rejected_before_a_partial_plan_can_be_consumed():
    with pytest.raises(NotImplementedError, match="mapping"):
        plan_animator_delegate(max_update_count=1, mapping_count=1)


@pytest.mark.parametrize("value", [None, True, 1.0, -(2**31) - 1, 65537])
def test_delegate_step_count_adapter_rejects_invalid_or_excessive_count(value):
    with pytest.raises(ValueError, match="bounded integer"):
        plan_animator_delegate(max_update_count=value, mapping_count=0)


@pytest.mark.parametrize("value", [None, True, 1.0, -(2**31) - 1, 2**31])
def test_delegate_mapping_count_adapter_uses_signed_int32(value):
    with pytest.raises(ValueError, match="bounded integer"):
        plan_animator_delegate(max_update_count=0, mapping_count=value)


def test_host_count_does_not_freeze_later_delegate_count_or_merge_async_boundaries():
    mode = FrameMode(True, True)
    host = plan_cloth_update(
        mode,
        is_playing=True,
        enabled_team_count=1,
        max_update_count=7,
        mapping_count=cast(Any, None),  # Deliberately absent, unselected host input.
    )
    delegate = plan_animator_delegate(max_update_count=1, mapping_count=0)
    after = plan_after_update(mode, active_team_count=1)
    outer = next(e for e in host.events if e.call == "DoAllInOneJob")
    assert outer.handle == host.master_handle
    assert outer.step_count is None
    assert sum(e.call == "SimulationStepUpdate" for e in delegate.events) == 1
    assert delegate.returns_job_handle is False
    assert calls(after) == [
        "CameraCullingPostProcess",
        "CompleteCrossFrame",
        "ClearMasterJob",
        "UpdateTeamAnimatorData",
    ]
    # These are separate observed phases, not proof of actual native execution.
    assert "UpdateTeamAnimatorData" not in calls(host) + calls(delegate)
