"""Fresh candidate core Team layout; never an observed official allocator."""

import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_official_physics_team_layout import build_document, export_file
from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    plan_particle_registration,
)
from official_physics_team_layout import (
    CandidateCoreGroup,
    Chunk,
    build_fresh_candidate_core_layout,
)
from official_physics_work_lists import StepTeam, build_step_work_lists


def group(name: str, count: int, **updates: Any) -> CandidateCoreGroup:
    return replace(
        CandidateCoreGroup(
            name=name,
            component_identity=f"identity:{name}",
            proxy_transform_count=count + 1,
            proxy_common_count=count,
            proxy_mesh_count=count,
            proxy_skin_bone_count=count,
            baseline_count=2,
            baseline_data_count=3,
            particle_count=count,
            distance_start_count=count,
            distance_data_count=count - 1,
        ),
        **updates,
    )


def test_fresh_layout_uses_independent_prefix_cursors_and_supplied_team_ids():
    layout = build_fresh_candidate_core_layout(
        (group("hair", 3), group("skirt", 5, baseline_count=4)),
        team_ids=(7, 11),
        fresh_empty_arenas=True,
    )
    hair, skirt = layout.teams
    assert (hair.team_id, skirt.team_id) == (7, 11)
    assert hair.proxy_transform == Chunk(0, 4)
    assert skirt.proxy_transform == Chunk(4, 6)
    assert hair.proxy_common == hair.proxy_mesh == hair.proxy_skin_bone == Chunk(0, 3)
    assert (
        skirt.proxy_common == skirt.proxy_mesh == skirt.proxy_skin_bone == Chunk(3, 5)
    )
    assert hair.baseline == Chunk(0, 2)
    assert skirt.baseline == Chunk(2, 4)
    assert hair.baseline_data == Chunk(0, 3)
    assert skirt.baseline_data == Chunk(3, 3)
    assert hair.particle == Chunk(0, 3)
    assert skirt.particle == Chunk(3, 5)
    assert hair.distance_start == Chunk(0, 3)
    assert skirt.distance_start == Chunk(3, 5)
    assert hair.distance_data == Chunk(0, 2)
    assert skirt.distance_data == Chunk(2, 4)
    assert layout.capacities == {
        "proxy_transform": 10,
        "proxy_common": 8,
        "proxy_mesh": 8,
        "proxy_skin_bone": 8,
        "baseline": 6,
        "baseline_data": 6,
        "particle": 8,
        "distance_start": 8,
        "distance_data": 6,
    }


def test_layout_drives_existing_registration_and_whole_chunk_worklists():
    layout = build_fresh_candidate_core_layout(
        (group("hair", 3), group("skirt", 2, baseline_count=1)),
        team_ids=(1, 2),
        fresh_empty_arenas=True,
    )
    for team in layout.teams:
        allocation = ParticleAllocation(team.particle.start, team.particle.count)
        plan = plan_particle_registration(
            team.particle.count,
            team.team_id,
            {name: allocation for name in PARTICLE_ARRAY_FIELDS},
            manager_valid=True,
            array_capacities={
                name: layout.capacities["particle"] for name in PARTICLE_ARRAY_FIELDS
            },
        )
        assert plan.particle_chunk == allocation
        assert plan.original_team_id == team.team_id

    teams = {
        team.team_id: StepTeam(
            0xAF,
            team.particle.start,
            team.particle.count,
            team.baseline.start,
            team.baseline.count,
        )
        for team in layout.teams
    }
    work = build_step_work_lists(
        teams,
        particle_team_order=(1, 2),
        baseline_team_order=(1, 2),
        particle_output_capacity=layout.capacities["particle"],
        baseline_output_capacity=layout.capacities["baseline"],
    )
    assert work.particle_indices == (0, 1, 2, 3, 4)
    assert work.baseline_indices == (0x10000, 0x10001, 0x20002)


@pytest.mark.parametrize(
    "groups,ids,premise",
    [
        ((group("a", 1),), (1,), False),
        ((group("a", 1),), (), True),
        ((group("a", 1), group("b", 1)), (1, 1), True),
        ((group("a", 1),), (0,), True),
        ((group("a", 1),), (32768,), True),
        ((group("a", 1), group("a", 1)), (1, 2), True),
        (
            (group("a", 1), group("b", 1, component_identity="identity:a")),
            (1, 2),
            True,
        ),
    ],
)
def test_layout_rejects_ambiguous_candidate_identity_or_premises(groups, ids, premise):
    with pytest.raises(ValueError):
        build_fresh_candidate_core_layout(
            groups, team_ids=ids, fresh_empty_arenas=premise
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"proxy_transform_count": 1},
        {"proxy_mesh_count": 2},
        {"proxy_skin_bone_count": 2},
        {"particle_count": 2},
        {"distance_start_count": 2},
        {"baseline_count": -1},
        {"distance_data_count": True},
    ],
)
def test_layout_rejects_counts_that_break_the_certified_core_domain(updates):
    with pytest.raises(ValueError):
        build_fresh_candidate_core_layout(
            (group("a", 3, **updates),),
            team_ids=(1,),
            fresh_empty_arenas=True,
        )


def source_documents() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    groups = []
    baseline_groups = []
    distance_groups = []
    for label, count, baseline_count, baseline_data, distance_data in (
        ("hair", 3, 2, 3, 2),
        ("skirt", 2, 1, 1, 4),
    ):
        identity = f"identity:{label}"
        groups.append(
            {
                "name": label,
                "component_identity": identity,
                "skin_bone_count": count,
                "runtime_instance_ids": list(range(count + 1)),
            }
        )
        baseline_groups.append(
            {
                "name": label,
                "component_identity": identity,
                "skin_bone_count": count,
                "baselines": {
                    "flags": [0] * baseline_count,
                    "starts": [0] * baseline_count,
                    "counts": [0] * baseline_count,
                    "data": [0] * baseline_data,
                },
            }
        )
        distance_groups.append(
            {
                "name": label,
                "component_identity": identity,
                "skin_bone_count": count,
                "distance": {
                    "words": [0] * count,
                    "data": [0] * distance_data,
                    "signed_rest_lengths": [1.0] * distance_data,
                    "pre_length_entry_count": distance_data,
                },
            }
        )
    states = ("rest", "posed")
    imports = {
        "schema_version": 1,
        "getter_scope": "scope",
        "states": [{"name": state, "groups": deepcopy(groups)} for state in states],
        "full_proxy_inputs_generated": False,
    }
    baselines = {
        "schema_version": 1,
        "getter_scope": "scope",
        "states": [
            {"name": state, "groups": deepcopy(baseline_groups)} for state in states
        ],
        "baseline_reference_generated": True,
        "full_proxy_inputs_generated": False,
    }
    distances = {
        "schema_version": 1,
        "getter_scope": "scope",
        "states": [
            {"name": state, "groups": deepcopy(distance_groups)} for state in states
        ],
        "distance_reference_generated": True,
        "full_proxy_inputs_generated": False,
    }
    return imports, baselines, distances


def test_export_document_publishes_fresh_candidate_core_layout_and_lists():
    document = build_document(
        *source_documents(),
        fresh_empty_arenas=True,
        sequential_candidate_team_ids=True,
    )
    assert document["team_ids"] == [1, 2]
    assert document["capacities"]["particle"] == 5
    assert document["capacities"]["baseline"] == 3
    assert document["teams"][1]["particle"] == {"start": 3, "count": 2}
    assert document["candidate_work_lists"]["particle_indices"] == [0, 1, 2, 3, 4]
    assert document["candidate_work_lists"]["baseline_indices"] == [
        0x10000,
        0x10001,
        0x20002,
    ]
    assert document["fresh_candidate_core_layout_generated"] is True
    assert document["original_runtime_team_ids_observed"] is False
    assert document["original_runtime_chunks_observed"] is False
    assert document["native_arrays_published"] is False


def test_export_document_refuses_state_topology_drift_and_false_premises():
    imports, baselines, distances = source_documents()
    distances["states"][1]["groups"][0]["distance"]["data"].append(2)
    distances["states"][1]["groups"][0]["distance"]["signed_rest_lengths"].append(2)
    with pytest.raises(ValueError):
        build_document(
            imports,
            baselines,
            distances,
            fresh_empty_arenas=True,
            sequential_candidate_team_ids=True,
        )
    with pytest.raises(ValueError):
        build_document(
            *source_documents(),
            fresh_empty_arenas=False,
            sequential_candidate_team_ids=True,
        )


def test_export_file_verifies_seals_and_refuses_overwrite(tmp_path):
    import hashlib
    import json

    paths = []
    seals = []
    for index, document in enumerate(source_documents()):
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(path)
        seals.append(hashlib.sha256(path.read_bytes()).hexdigest())
    output = tmp_path / "layout.json"
    export_file(
        paths[0],
        paths[1],
        paths[2],
        output,
        tuple(seals),
        fresh_empty_arenas=True,
        sequential_candidate_team_ids=True,
    )
    assert output.exists()
    with pytest.raises(FileExistsError):
        export_file(
            paths[0],
            paths[1],
            paths[2],
            output,
            tuple(seals),
            fresh_empty_arenas=True,
            sequential_candidate_team_ids=True,
        )
    with pytest.raises(ValueError):
        export_file(
            paths[0],
            paths[1],
            paths[2],
            tmp_path / "other.json",
            ("0" * 64, *seals[1:]),
            fresh_empty_arenas=True,
            sequential_candidate_team_ids=True,
        )
