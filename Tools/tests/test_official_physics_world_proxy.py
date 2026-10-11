"""Source-ordered finite skinning + independent row-oriented Single reference."""

import math
import random
import struct
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_bindpose import ImportedBoneWeight
from official_physics_particle_init import initialize_registered_particle_window
from official_physics_particle_registration import (
    PARTICLE_ARRAY_FIELDS,
    ParticleAllocation,
    plan_particle_registration,
)
from official_physics_particle_reset import ParticleFrameState, ParticleResetTeam
from official_physics_world_proxy import (
    ProxyUpdateTeam,
    WorldProxyBuffers,
    build_proxy_update_vertices,
    multiply_frame_columns_single,
    skin_proxy_vertex,
    update_world_proxy,
    weight_prefix_count,
)

I = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
UP, FORWARD = (0, 1, 0), (0, 0, 1)
ONE = ImportedBoneWeight((1, 0, 0, 0), (0, -99, -99, -99))


def f(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(values):
    return tuple(struct.pack("<f", v) for v in values)


def translation(x):
    return I[:3] + ((x, 0, 0, 1),)


def row_reference(matrix, columns):
    # Intentionally does not import production matrix/rounding helpers.
    rows = list(zip(*matrix, strict=True))
    output = []
    for column in columns:
        result = []
        for row in rows:
            products = [f(f(a) * f(b)) for a, b in zip(row, column, strict=True)]
            acc = products[0]
            for value in products[1:]:
                acc = f(acc + value)
            result.append(acc)
        output.append(tuple(result))
    return tuple(output)


def skin(
    position=(1, 2, 3),
    normal=UP,
    tangent=FORWARD,
    weight=ONE,
    bindposes=(I,),
    indices=(0,),
    current=(I,),
    **kwargs
):
    return skin_proxy_vertex(
        position, normal, tangent, weight, bindposes, indices, current, **kwargs
    )


@pytest.mark.parametrize(
    "weights,count",
    [
        ((0, 0, 0, 0), 0),
        ((-1, -2, -3, -4), 0),
        ((1, 0, 0, 0), 1),
        ((0, 1, 0, 0), 2),
        ((1, 0, 1, 0), 3),
        ((-1, 0, 0, 1), 4),
        ((1, 1, 0, -1), 2),
        ((1e-50, 0, 0, 0), 0),
    ],
)
def test_highest_strict_positive_single_weight_prefix(weights, count):
    assert weight_prefix_count(weights) == count


@pytest.mark.parametrize(
    "weights", [(1, 2, 3), (1, 2, 3, 4, 5), (True, 0, 0, 0), (math.inf, 0, 0, 0)]
)
def test_invalid_weights_are_not_normalized_or_sanitized(weights):
    with pytest.raises(ValueError):
        weight_prefix_count(weights)


def test_identity_single_position_and_reconstructed_frame():
    p, q = skin(position=(1000000000.25, 2, 3))
    assert p == (1000000000, 2, 3) and q == (0, 0, 0, 1)


def test_two_matrix_applications_not_precomposed():
    p, _ = skin(
        position=(1, 2, 3),
        bindposes=(translation(2**24),),
        current=(translation(-(2**24)),),
    )
    assert p == (0, 2, 3)  # Precomposition would give (1,2,3).


def test_homogeneous_w_survives_both_multiplications():
    bind = I[:3] + ((0, 0, 0, 2),)
    assert skin(position=(3, 2, 1), bindposes=(bind,), current=(translation(10),))[
        0
    ] == (23, 2, 1)


def test_raw_weights_and_negative_prefix_contribute():
    weight = ImportedBoneWeight((-1, 0, 2, 0), (0, 1, 2, -99))
    assert skin(
        position=(1, 2, 3),
        weight=weight,
        bindposes=(I, I, I),
        indices=(0, 1, 2),
        current=(translation(10), I, translation(20)),
    )[0] == (31, 2, 3)
    assert skin(weight=ImportedBoneWeight((2, 0, 0, 0), (0, 0, 0, 0)))[0] == (2, 4, 6)


def test_zero_prefix_still_reads_indices_and_matrix():
    weight = ImportedBoneWeight((1, 0, 0.5, 0), (0, 99, 2, 0))
    with pytest.raises(ValueError):
        skin(weight=weight, bindposes=(I, I, I), indices=(0, 1, 2), current=(I, I, I))


def test_weight_prefix_order_is_not_sorted_by_bone_index():
    current = (translation(2**24), translation(-(2**24)), translation(1))
    weight = ImportedBoneWeight((1, 1, 1, 0), (0, 1, 2, 0))
    assert skin(
        position=(0, 0, 0),
        weight=weight,
        bindposes=(I, I, I),
        indices=(0, 1, 2),
        current=current,
    )[0] == (1, 0, 0)
    reordered = ImportedBoneWeight((1, 1, 1, 0), (0, 2, 1, 0))
    assert skin(
        position=(0, 0, 0),
        weight=reordered,
        bindposes=(I, I, I),
        indices=(0, 1, 2),
        current=current,
    )[0] == (0, 0, 0)


def test_separate_normalization_retains_axis_convention_and_reflection():
    assert skin(normal=(0, 3, 0), tangent=(0, 0, 2))[1] == (0, 0, 0, 1)
    reflection = ((-1, 0, 0, 0),) + I[1:]
    assert skin(current=(reflection,)) == ((-1, 2, 3), (0, 0, 0, 1))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"normal": (0, 0, 0)},
        {"tangent": (0, 0, 0)},
        {"normal": (0, 0, 1)},
        {"normal": (0, 1e-30, 0)},
        {"normal": (0, 1e30, 0)},
        {"position": (math.nan, 0, 0)},
        {"weight": ImportedBoneWeight((0, 0, 0, 0), (0, 0, 0, 0))},
        {"weight": ImportedBoneWeight((1, 0, 0, 0), cast(Any, (0, 0, 0)))},
        {"skin_start": -1},
        {"transform_start": True},
        {"indices": (-1,)},
        {"bindposes": ()},
        {"current": ()},
        {"current": (I[:3],)},
    ],
)
def test_degenerate_or_bad_selected_inputs_fail_without_identity_fallback(kwargs):
    with pytest.raises(ValueError):
        skin(**kwargs)


def test_three_columns_match_independent_row_arithmetic():
    rng = random.Random(10411)
    for _ in range(25):
        matrix = tuple(tuple(f(rng.uniform(-9, 9)) for _ in range(4)) for _ in range(4))
        cols = tuple(tuple(f(rng.uniform(-9, 9)) for _ in range(4)) for _ in range(3))
        actual = multiply_frame_columns_single(matrix, cols)
        expected = row_reference(matrix, cols)
        assert tuple(map(bits, actual)) == tuple(map(bits, expected))


@pytest.mark.parametrize("columns", [(), I, ((1, 2, 3),) * 3])
def test_three_column_shape_is_explicit(columns):
    with pytest.raises(ValueError):
        multiply_frame_columns_single(I, columns)


def mapped_fixture():
    # Four independent chunk starts and an unrelated prefix in every input arena.
    team = ProxyUpdateTeam(0, 8, 3, 1, 5, 6)
    buffers = WorldProxyBuffers(
        ((999, 999, 999),) * 5 + ((1, 2, 3),),
        ((999, 999, 999),) * 5 + (UP,),
        ((999, 999, 999),) * 5 + (FORWARD,),
        (ONE,) * 6,
        (-99,) * 6 + (2,),
        (I,) * 7,
        (I,) * 10 + (translation(10),),
    )
    return team, buffers


def update(
    vertices=(3,),
    *,
    teams=None,
    team_ids=(0, 0, 0, 7, 0),
    buffers=None,
    previous_positions=((91.25, 92, 93),) * 5,
    previous_rotations=((0, 0, 0, 2),) * 5
):
    team, inputs = mapped_fixture()
    return update_world_proxy(
        vertices,
        teams if teams is not None else {7: team},
        team_ids,
        buffers or inputs,
        previous_positions,
        previous_rotations,
    )


def test_differential_four_chunk_mapping_and_unlisted_outputs_preserved():
    result = update((3, 3))
    assert result.written_vertices == (3, 3)  # Not silently deduplicated.
    assert result.positions[3] == (11, 2, 3) and result.rotations[3] == (0, 0, 0, 1)
    assert result.positions[:3] == ((91.25, 92, 93),) * 3
    assert result.rotations[:3] == ((0, 0, 0, 2),) * 3
    assert result.positions[4] == (91.25, 92, 93)
    # Kernel consumes supplied list; flag0 does NOT filter this slot again.


def test_empty_update_does_not_read_missing_arenas_or_team_data():
    result = update(
        (), teams={}, team_ids=(), buffers=WorldProxyBuffers((), (), (), (), (), (), ())
    )
    assert result.written_vertices == ()
    assert result.positions == ((91.25, 92, 93),) * 5


def test_current_matrix_changes_while_bindpose_stays_fixed():
    _, inputs = mapped_fixture()
    first = update(buffers=inputs)
    changed = replace(inputs, transform_local_to_world=(I,) * 10 + (translation(20),))
    second = update(
        buffers=changed,
        previous_positions=first.positions,
        previous_rotations=first.rotations,
    )
    assert second.positions[3] == (21, 2, 3)
    assert inputs.skin_bone_bindposes is changed.skin_bone_bindposes


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vertices": (True,)},
        {"vertices": (5,)},
        {"vertices": (2,)},
        {"team_ids": ()},
        {"teams": {}},
        {"team_ids": (0, 0, 0, 0, 0)},
        {"team_ids": (0, 0, 0, 32768, 0)},
        {"previous_rotations": ()},
    ],
)
def test_selected_global_identity_or_window_inconsistency_rejected(kwargs):
    with pytest.raises(ValueError):
        update(**kwargs)


def test_insufficient_mesh_arenas_or_chunk_overflow_rejected():
    team, buffers = mapped_fixture()
    with pytest.raises(ValueError):
        update(buffers=replace(buffers, local_tangents=()))
    with pytest.raises(ValueError):
        update(teams={7: replace(team, proxy_common_count=2**31 - 1)})
    with pytest.raises(ValueError, match="common window"):
        update(teams={7: replace(team, proxy_common_start=4)})


def test_proxy_list_gate_is_not_step_gate_and_keeps_block_order():
    teams = {
        7: ProxyUpdateTeam(2 | 0x10, 0, 3, 2, 0, 0),
        9: ProxyUpdateTeam(2, 0, 15, 1, 0, 0),
    }
    assert build_proxy_update_vertices(
        teams, team_order=(0, 9, 7, 9), output_capacity=4
    ) == (15, 3, 4, 15)


@pytest.mark.parametrize("flag", [0, 0xA0, 2 | (1 << 61), 2 | 0x800, 2 | 0x80000])
def test_inactive_proxy_list_never_reads_invalid_chunk(flag):
    team = ProxyUpdateTeam(flag, -1, -1, -1, -1, -1)
    assert (
        build_proxy_update_vertices({7: team}, team_order=(7,), output_capacity=0) == ()
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"teams": {}, "team_order": (7,)},
        {"team_order": (32768,)},
        {"team_order": (True,)},
        {"output_capacity": True},
        {"output_capacity": 0},
        {"teams": {7: ProxyUpdateTeam(-1, 0, 0, 1, 0, 0)}},
        {"teams": {7: ProxyUpdateTeam(2, 0, -1, 1, 0, 0)}},
        {"teams": {7: ProxyUpdateTeam(2, 0, 2**31 - 1, 2, 0, 0)}},
    ],
)
def test_proxy_list_adapter_ranges_and_explicit_output_capacity(kwargs):
    inputs = {
        "teams": {7: ProxyUpdateTeam(2, 0, 3, 1, 0, 0)},
        "team_order": (7,),
        "output_capacity": 1,
    }
    inputs.update(kwargs)
    with pytest.raises(ValueError):
        build_proxy_update_vertices(**inputs)


def test_empty_and_team_zero_lists_skip_without_tables():
    assert build_proxy_update_vertices({}, team_order=(0,), output_capacity=0) == ()
    assert (
        build_proxy_update_vertices(
            {7: ProxyUpdateTeam(2, 0, 0, 0, 0, 0)}, team_order=(7,), output_capacity=0
        )
        == ()
    )


def test_world_producer_output_feeds_sparse_registration_reset14():
    world = update()
    plan = plan_particle_registration(
        1,
        7,
        {n: ParticleAllocation(2, 1) for n in PARTICLE_ARRAY_FIELDS},
        manager_valid=True,
        array_capacities={n: 5 for n in PARTICLE_ARRAY_FIELDS},
    )
    dirty = ParticleFrameState(
        *(
            [
                (91, 92, 93),
                (81, 82, 83),
                (0, 0, 0, 2),
                (71, 72, 73),
                (0, 0, 0, 3),
                (61, 62, 63),
                (0, 0, 0, 4),
                (51, 52, 53),
                (41, 42, 43),
                (31, 32, 33),
                (21, 22, 23),
                0.8,
                0.9,
                (11, 12, 13),
            ]
        )
    )
    result = initialize_registered_particle_window(
        plan,
        (dirty,) * 5,
        team_id=7,
        enabled_team=ParticleResetTeam(15, 2, 3),
        proxy_world_positions=world.positions,
        proxy_world_rotations=world.rotations,
        world_proxy_pose_confirmed=True,
    )
    assert result.fully_reset and len(result.results[0].writes) == 14
    assert result.states[0].next_position == (11, 2, 3)
    assert result.states[0].base_rotation == (0, 0, 0, 1)
    assert result.states[0].velocity == (0, 0, 0) and result.states[0].friction == 0
