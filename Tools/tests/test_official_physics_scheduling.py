"""Static-source ordering fixtures; no native jobs or Unity physics executed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_publication import TransformBufferSnapshot, copy_double_buffer
from official_physics_scheduling import (
    FrameMode,
    plan_after_update,
    plan_cloth_update,
    plan_complete_master,
    plan_early_update,
    should_update_cloth,
)


def calls(plan):
    return [event.call for event in plan.events]


ORDINARY = FrameMode(False, False)


def cloth(mode=ORDINARY, **kwargs):
    values = {"is_playing": True, "enabled_team_count": 1, "max_update_count": 2}
    return plan_cloth_update(mode, **(values | kwargs))


CHAIN = [
    "PreProxyMeshUpdate",
    "CalcCenterAndInertiaAndWind",
    "PreSimulationUpdate",
    "Collider.PreSimulationUpdate",
    "SimulationStepUpdate",
    "SimulationStepUpdate",
    "CalcDisplayPosition",
    "PostProxyMeshUpdate",
]


def test_ordinary_current_write_is_after_display_and_proxy_before_completion():
    plan = cloth(pre_callback=True, post_callback=True)
    assert calls(plan) == [
        "OnPreSimulation",
        "FrameUpdate",
        "AlwaysTeamUpdate",
        "AlwaysWindUpdate",
        "WorkBufferUpdate",
        "ClearMasterJob",
        "ReadTransform",
        *CHAIN,
        "WriteTransform",
        "Collider.PostSimulationUpdate",
        "PostTeamUpdate",
        "CameraCullingPreProcess",
        "CompleteOrdinary",
        "ClearMasterJob",
        "OnPostSimulation",
    ]
    assert plan.master_handle == "default"


def test_cross_frame_consumes_last_before_new_solver_and_publishes_after_proxy():
    plan = cloth(FrameMode(True, False), post_callback=True)
    assert calls(plan) == [
        "FrameUpdate",
        "CompleteCrossFrame",
        "ClearMasterJob",
        "AlwaysTeamUpdate",
        "AlwaysWindUpdate",
        "WorkBufferUpdate",
        "ClearMasterJob",
        "ReadTransform",
        "WriteDoubleBufferTransform",
        "CompleteOrdinary",
        "ValidPosition",
        *CHAIN,
        "CopyDoubleBuffer",
        "Collider.PostSimulationUpdate",
        "PostTeamUpdate",
        "CameraCullingPreProcess",
        "CompleteOrdinary",
        "OnPostSimulation",
    ]
    assert plan.master_handle != "default"
    schedules = [e for e in plan.events if e.kind == "schedule"]
    read, last_write, valid = schedules[:3]
    assert read.depends_on == "default"
    assert last_write.depends_on == read.handle
    assert valid.depends_on == "default"  # Host barrier, not a last-write job edge.
    assert schedules[-1].handle == plan.master_handle
    completions = [e for e in plan.events if e.kind == "complete-if-nonzero"]
    assert [e.handle for e in completions] == [
        "incoming-master",
        last_write.handle,
        last_write.handle,
    ]
    # Two condition CHECK sites, not an assertion native Complete runs twice.


@pytest.mark.parametrize("mode", [FrameMode(False, False), FrameMode(True, False)])
def test_solver_dependencies_are_threaded_without_current_last_alias_swap(mode):
    jobs = [e for e in cloth(mode).events if e.kind == "schedule"]
    start = 2 if mode.cross_frame else 0
    assert jobs[start].depends_on == "default"
    for previous, current in zip(jobs[start:], jobs[start + 1 :]):
        assert current.depends_on == previous.handle
    assert len({e.handle for e in jobs}) == len(jobs)


@pytest.mark.parametrize("count", [0, -1, -(2**31), 1, 4])
def test_step_loop_uses_post_team_max_count_and_zero_based_index(count):
    jobs = [
        e
        for e in cloth(max_update_count=count).events
        if e.call == "SimulationStepUpdate"
    ]
    assert [(e.step_count, e.step_index) for e in jobs] == [
        (count, i) for i in range(max(0, count))
    ]
    assert "CalcDisplayPosition" in calls(cloth(max_update_count=count))


@pytest.mark.parametrize(
    "mode", [FrameMode(False, False), FrameMode(True, False), FrameMode(True, True)]
)
def test_not_playing_has_no_callbacks_completion_or_input_reads(mode):
    plan = cloth(
        mode,
        is_playing=False,
        enabled_team_count=None,
        max_update_count=None,
        mapping_count=None,
        pre_callback=True,
        post_callback=True,
    )
    assert plan.events == ()
    assert plan.master_handle == "incoming-master"


@pytest.mark.parametrize("cross", [False, True])
def test_no_enabled_team_returns_after_team_update_without_post_callback(cross):
    plan = cloth(
        FrameMode(cross, True),
        enabled_team_count=0,
        max_update_count=None,
        mapping_count=None,
        pre_callback=True,
        post_callback=True,
    )
    expected = ["OnPreSimulation", "FrameUpdate"]
    if cross:
        expected += ["CompleteCrossFrame", "ClearMasterJob"]
    assert calls(plan) == expected + ["AlwaysTeamUpdate"]
    assert plan.master_handle == ("default" if cross else "incoming-master")


def test_animator_flag_alone_does_not_select_cross_frame_animator_route():
    assert cloth(FrameMode(False, True)) == cloth(FrameMode(False, False))


def test_live_cross_animator_route_explicitly_unported_not_ordinary_fallback():
    with pytest.raises(NotImplementedError, match="Animator"):
        cloth(FrameMode(True, True))


def test_mesh_mapping_route_explicitly_unported_not_silently_dropped():
    with pytest.raises(NotImplementedError, match="mapping"):
        cloth(mapping_count=1)


@pytest.mark.parametrize(
    "cross,complete", [(False, "CompleteOrdinary"), (True, "CompleteCrossFrame")]
)
def test_complete_master_selects_distinct_icalls_and_always_clears(cross, complete):
    plan = plan_complete_master(FrameMode(cross, False))
    assert calls(plan) == [complete, "ClearMasterJob"]
    assert plan.events[0].kind == "complete-if-nonzero"
    assert plan.events[0].handle == "incoming-master"
    assert plan.master_handle == "default"


@pytest.mark.parametrize("cross", [False, True])
def test_early_update_restores_even_without_enabled_team_when_processes_exist(cross):
    plan = plan_early_update(
        FrameMode(cross, False), process_count=1, enabled_team_count=0
    )
    prefix = ["CompleteCrossFrame", "ClearMasterJob"] if cross else []
    assert calls(plan) == prefix + ["RestoreTransform", "CompleteOrdinary"]
    assert plan.events[-1].handle == plan.events[-2].handle
    assert plan.events[-2].depends_on == "default"
    assert plan.master_handle == ("default" if cross else "incoming-master")


def test_early_culling_precedes_restore_and_no_publish_occurs():
    assert calls(
        plan_early_update(FrameMode(True, False), process_count=2, enabled_team_count=1)
    ) == [
        "CompleteCrossFrame",
        "ClearMasterJob",
        "CameraCullingPostProcess",
        "RestoreTransform",
        "CompleteOrdinary",
    ]


@pytest.mark.parametrize(
    "mode,count", [(FrameMode(True, False), 0), (FrameMode(True, True), 1)]
)
def test_early_return_does_not_restore_or_consume_unused_enabled_count(mode, count):
    assert (
        plan_early_update(mode, process_count=count, enabled_team_count=None).events
        == ()
    )


@pytest.mark.parametrize("count", [0, 2])
def test_after_update_animator_culling_then_complete_then_update_data(count):
    plan = plan_after_update(FrameMode(True, True), active_team_count=count)
    prefix = ["CameraCullingPostProcess"] if count else []
    assert calls(plan) == prefix + [
        "CompleteCrossFrame",
        "ClearMasterJob",
        "UpdateTeamAnimatorData",
    ]
    assert plan.master_handle == "default"


@pytest.mark.parametrize(
    "mode", [FrameMode(False, False), FrameMode(False, True), FrameMode(True, False)]
)
def test_after_update_other_modes_do_not_read_count(mode):
    assert plan_after_update(mode, active_team_count=None).events == ()


@pytest.mark.parametrize(
    "location,before,expected",
    [
        (0, False, True),
        (0, True, False),
        (1, False, False),
        (1, True, True),
        (2, False, False),
        (-1, True, False),
    ],
)
def test_late_hook_raw_enum_equality_and_only_one_matching_hook(
    location, before, expected
):
    assert should_update_cloth(location, before_late=before) is expected


@pytest.mark.parametrize("value", [0, 1, None, "true"])
@pytest.mark.parametrize("field", ["cross_frame", "animator_transform"])
def test_mode_requires_actual_boolean_not_truthy_value(value, field):
    with pytest.raises(ValueError, match="boolean"):
        FrameMode(
            **({"cross_frame": False, "animator_transform": False} | {field: value})
        )


@pytest.mark.parametrize("field", ["is_playing", "pre_callback", "post_callback"])
def test_callback_play_flags_require_booleans(field):
    with pytest.raises(ValueError, match="boolean"):
        cloth(**{field: 1})


@pytest.mark.parametrize(
    "field", ["enabled_team_count", "mapping_count", "max_update_count"]
)
@pytest.mark.parametrize("value", [True, 1.0, None, 65537])
def test_count_adapter_policy_rejects_non_integer_or_unbounded_allocations(
    field, value
):
    with pytest.raises(ValueError, match="integer"):
        cloth(**{field: value})


@pytest.mark.parametrize("field", ["enabled_team_count", "mapping_count"])
def test_negative_collection_count_is_invalid_adapter_shape(field):
    with pytest.raises(ValueError, match="integer"):
        cloth(**{field: -1})


def test_negative_step_count_below_int32_rejected():
    with pytest.raises(ValueError, match="integer"):
        cloth(max_update_count=-(2**31) - 1)


@pytest.mark.parametrize("value", [True, 1.0, 2**31, -(2**31) - 1])
def test_late_location_rejects_non_int32(value):
    with pytest.raises(ValueError, match="integer"):
        should_update_cloth(value, before_late=True)


def test_late_hook_flag_requires_boolean():
    with pytest.raises(ValueError, match="boolean"):
        should_update_cloth(0, before_late=0)


def test_two_serial_synthetic_frames_consume_previous_snapshot_not_new_result():
    # Serial fixture deliberately does NOT claim native async execution or an oracle.
    q = ((0, 0, 0, 1),)

    def snapshot(x):
        return TransformBufferSnapshot(((x, 0, 0),), q, ((x, 0, 0),), q)

    last = snapshot(10)
    seen = []
    for next_value in (20, 30):
        current = snapshot(next_value)
        for event in cloth(FrameMode(True, False)).events:
            if event.call == "WriteDoubleBufferTransform":
                seen.append(last.world_positions[0][0])
            elif event.call == "CopyDoubleBuffer":
                last = copy_double_buffer(current, last)
    assert seen == [10, 20]
    assert last == snapshot(30)
