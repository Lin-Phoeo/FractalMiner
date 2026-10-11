"""Local Team1 world/reset references -> unified candidate global state."""

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_global_state import build_document, export_file

WRITES = [
    "next_position",
    "old_position",
    "old_rotation",
    "base_position",
    "base_rotation",
    "old_animation_position",
    "old_animation_rotation",
    "velocity_position",
    "display_position",
    "velocity",
    "real_velocity",
    "friction",
    "static_friction",
    "collision_normal",
]


def particle_state(value: int) -> dict:
    vector = [value, value + 1, value + 2]
    rotation = [0, 0, 0, 1]
    return {
        "next_position": vector,
        "old_position": vector,
        "old_rotation": rotation,
        "base_position": vector,
        "base_rotation": rotation,
        "old_animation_position": vector,
        "old_animation_rotation": rotation,
        "velocity_position": vector,
        "display_position": vector,
        "velocity": [0, 0, 0],
        "real_velocity": [0, 0, 0],
        "friction": 0,
        "static_friction": 0,
        "collision_normal": [0, 0, 0],
    }


def documents() -> tuple[dict, dict]:
    teams = []
    groups = []
    cursor = 0
    transform_cursor = 0
    baseline_cursor = 0
    baseline_data_cursor = 0
    distance_data_cursor = 0
    for team_id, (name, count) in enumerate((("hair", 2), ("skirt", 3)), start=1):
        identity = f"identity:{name}"
        teams.append(
            {
                "team_id": team_id,
                "name": name,
                "component_identity": identity,
                "proxy_transform": {"start": transform_cursor, "count": count + 1},
                "proxy_common": {"start": cursor, "count": count},
                "proxy_mesh": {"start": cursor, "count": count},
                "proxy_skin_bone": {"start": cursor, "count": count},
                "baseline": {"start": baseline_cursor, "count": 1},
                "baseline_data": {"start": baseline_data_cursor, "count": count},
                "particle": {"start": cursor, "count": count},
                "distance_start": {"start": cursor, "count": count},
                "distance_data": {"start": distance_data_cursor, "count": count - 1},
            }
        )
        states = [particle_state(team_id * 10 + local) for local in range(count)]
        groups.append(
            {
                "name": name,
                "component_identity": identity,
                "skin_bone_count": count,
                "runtime_instance_ids": list(range(count + 1)),
                "matrix_identities": [f"m:{name}:{i}" for i in range(count + 1)],
                "experiment_team": {
                    "flag": 15,
                    "proxy_transform_start": 0,
                    "proxy_common_start": 0,
                    "proxy_common_count": count,
                    "proxy_mesh_start": 0,
                    "proxy_skin_bone_start": 0,
                },
                "world": {
                    "positions": [[team_id, i, 0] for i in range(count)],
                    "rotations": [[0, 0, 0, 1] for _ in range(count)],
                    "written_vertices": list(range(count)),
                },
                "reset": {
                    "particle_start": 0,
                    "states": states,
                    "results": [
                        {
                            "state": state,
                            "writes": WRITES,
                            "proxy_index": local,
                            "reset_applied": True,
                        }
                        for local, state in enumerate(states)
                    ],
                    "fully_reset": True,
                },
            }
        )
        cursor += count
        transform_cursor += count + 1
        baseline_cursor += 1
        baseline_data_cursor += count
        distance_data_cursor += count - 1
    capacities = {
        "proxy_transform": transform_cursor,
        "proxy_common": cursor,
        "proxy_mesh": cursor,
        "proxy_skin_bone": cursor,
        "baseline": baseline_cursor,
        "baseline_data": baseline_data_cursor,
        "particle": cursor,
        "distance_start": cursor,
        "distance_data": distance_data_cursor,
    }
    layout = {
        "schema_version": 1,
        "getter_scope": "scope",
        "state_names": ["rest", "posed"],
        "team_ids": [1, 2],
        "teams": teams,
        "capacities": capacities,
        "fresh_candidate_core_layout_generated": True,
        "state_topology_invariant": True,
        "original_runtime_team_ids_observed": False,
        "original_runtime_chunks_observed": False,
        "native_arrays_published": False,
        "input_sha256": {"imports": "1" * 64},
    }
    world = {
        "schema_version": 1,
        "getter_scope": "scope",
        "states": [
            {"name": name, "groups": deepcopy(groups)} for name in ("rest", "posed")
        ],
        "supplied_input_world_reference_generated": True,
        "supplied_world_first_reset_reference_generated": True,
        "full_proxy_inputs_generated": False,
        "native_arrays_published": False,
        "official_solver_integrated": False,
        "changing_animation_verified": False,
        "original_runtime_executed": False,
        "stage_modified": False,
        "input_sha256": {"imports": "1" * 64, "getters": "2" * 64},
    }
    return world, layout


def test_global_state_remaps_every_group_without_team_or_slot_aliasing():
    output = build_document(*documents(), candidate_global_remap=True)
    rest = output["states"][0]
    assert rest["particle_team_ids"] == [1, 1, 2, 2, 2]
    assert rest["proxy_team_ids"] == [1, 1, 2, 2, 2]
    assert rest["world_written_vertices"] == [0, 1, 2, 3, 4]
    assert rest["proxy_world_positions"] == [
        [1, 0, 0],
        [1, 1, 0],
        [2, 0, 0],
        [2, 1, 0],
        [2, 2, 0],
    ]
    assert [result["global_particle_index"] for result in rest["reset_results"]] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert [result["global_proxy_index"] for result in rest["reset_results"]] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert [result["team_id"] for result in rest["reset_results"]] == [1, 1, 2, 2, 2]
    assert rest["particle_states"] == [
        result["state"] for result in rest["reset_results"]
    ]
    assert output["candidate_global_world_reset_generated"] is True
    assert output["changing_animation_verified"] is False
    assert output["native_arrays_published"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda world, layout: layout["teams"][0].update(name=""),
        lambda world, layout: layout["capacities"].update(particle=True),
        lambda world, layout: layout["teams"][0].update(
            proxy_common={"start": 0, "count": 2, "extra": 0}
        ),
        lambda world, layout: layout["teams"][0].update(
            proxy_common={"start": 2**31 - 1, "count": 2}
        ),
        lambda world, layout: layout.update(native_arrays_published=True),
        lambda world, layout: layout["teams"][1].update(team_id=1),
        lambda world, layout: layout["teams"][1]["particle"].update(start=1),
        lambda world, layout: layout["capacities"].update(particle=99),
        lambda world, layout: world["states"][0]["groups"][0].update(
            component_identity="wrong"
        ),
        lambda world, layout: world["states"][0]["groups"][0].update(skin_bone_count=1),
        lambda world, layout: world["states"][0]["groups"][0]["experiment_team"].update(
            proxy_common_start=1
        ),
        lambda world, layout: world["states"][0]["groups"][0]["world"][
            "positions"
        ].pop(),
        lambda world, layout: world["states"][0]["groups"][0]["world"][
            "written_vertices"
        ].reverse(),
        lambda world, layout: world["states"][0]["groups"][0]["reset"].update(
            fully_reset=False
        ),
        lambda world, layout: world["states"][0]["groups"][0]["reset"]["results"][
            0
        ].update(proxy_index=1),
        lambda world, layout: world["states"][0]["groups"][0]["reset"]["results"][0][
            "writes"
        ].reverse(),
        lambda world, layout: world["states"][0]["groups"][0]["reset"]["results"][
            0
        ].update(state=particle_state(999)),
        lambda world, layout: world["states"][1]["groups"].pop(),
        lambda world, layout: world.pop("schema_version"),
    ],
)
def test_global_state_refuses_nonlocal_sources_or_noncontiguous_layout(mutate):
    world, layout = documents()
    mutate(world, layout)
    with pytest.raises(ValueError):
        build_document(world, layout, candidate_global_remap=True)


def test_global_state_requires_exact_boundary_flags_and_explicit_premise():
    world, layout = documents()
    world["changing_animation_verified"] = True
    with pytest.raises(ValueError):
        build_document(world, layout, candidate_global_remap=True)
    with pytest.raises(ValueError):
        build_document(*documents(), candidate_global_remap=False)


def test_export_file_seals_both_inputs_and_refuses_overwrite(tmp_path):
    paths = []
    seals = []
    for index, document in enumerate(documents()):
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(path)
        seals.append(hashlib.sha256(path.read_bytes()).hexdigest())
    output = tmp_path / "global.json"
    export_file(paths[0], paths[1], output, tuple(seals), candidate_global_remap=True)
    assert output.exists()
    with pytest.raises(FileExistsError):
        export_file(
            paths[0], paths[1], output, tuple(seals), candidate_global_remap=True
        )
    with pytest.raises(ValueError):
        export_file(
            paths[0],
            paths[1],
            tmp_path / "other.json",
            ("0" * 64, seals[1]),
            candidate_global_remap=True,
        )
