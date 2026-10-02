"""Ordinary bone build and proxy attribute fixtures, not a live-game oracle."""

import struct
import sys
from pathlib import Path
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_physics_saved_selection import (
    SavedSelection,
    apply_bone_proxy_selection,
    apply_proxy_selection_attributes,
    choose_bone_build_selection,
    proxy_selection_search_parameters,
    selection_is_valid,
)

P = ((0, 0, 0), (0, 1, 0))


@pytest.mark.parametrize(
    "positions,attributes,valid",
    [
        (None, None, False),
        (None, (2,), False),
        (P, None, False),
        ((), (), False),
        (P, (), False),
        ((), (2,), False),
        (P, (2,), False),
        (P, (1, 2, 3), False),
        (P, (0, 255), True),
    ],
)
@pytest.mark.parametrize("edited", [False, True])
def test_validity_is_array_shape_not_user_edit(positions, attributes, valid, edited):
    assert (
        selection_is_valid(SavedSelection(positions, attributes, -1, edited)) is valid
    )


@pytest.mark.parametrize("edited", [False, True])
def test_valid_saved_selection_is_cloned_even_when_unedited(edited):
    saved = SavedSelection(((0, 0, 0), (0, 2, 0), (0, 4, 0)), (128, 1, 4), 7, edited)
    result = choose_bone_build_selection(saved, P, 0.5, [0], [])
    assert result == saved and result is not saved
    # Valid saved point count need NOT equal current collected bone count.
    assert result.positions is not None and len(result.positions) == 3


def test_invalid_saved_selection_uses_proxy_constructor_not_generate_selection_api():
    result = choose_bone_build_selection(
        SavedSelection(None, None, 9, True), P, 1.25, [0], []
    )
    assert result == SavedSelection(P, (1, 2), 1.25, False)
    # userEdit=false from ordinary proxy constructor, not GenerateBone... true.
    assert result.user_edit is False


def test_saved_json_decimal_inputs_clone_as_original_single_not_python_double():
    saved = SavedSelection(((0.1, 0.2, -0.3),), (1,), 0.7, False)
    result = choose_bone_build_selection(saved, (), 0, (), ())
    assert result.positions is not None and saved.positions is not None
    assert struct.pack("<3f", *result.positions[0]) == struct.pack(
        "<3f", *saved.positions[0]
    )
    assert struct.pack("<f", result.max_connection_distance) == struct.pack(
        "<f", saved.max_connection_distance
    )


def test_override_is_full_byte_replacement_after_roots_and_applies_to_saved_branch():
    invalid = SavedSelection((), (), 0, False)
    generated = choose_bone_build_selection(invalid, P, 1, [0], [(0, 130), (-1, 255)])
    assert generated.attributes == (130, 2)
    saved = SavedSelection(P, (1, 2), 8, True)
    result = choose_bone_build_selection(saved, (), 0, (), [(1, 0), (1, 128)])
    assert result.attributes == (1, 128)
    assert saved.attributes == (1, 2) and result.max_connection_distance == 8


@pytest.mark.parametrize(
    "saved", [SavedSelection((), (), 0, True), SavedSelection(P, (2,), 0, False)]
)
def test_invalid_shape_fallback_and_empty_proxy_remains_invalid(saved):
    result = choose_bone_build_selection(saved, (), 0, (), ())
    assert result.positions == result.attributes == ()
    assert result.user_edit is False and not selection_is_valid(result)


@pytest.mark.parametrize(
    "roots,overrides",
    [
        ([-1], []),
        ([2], []),
        ([True], []),
        ([], [(2, 1)]),
        ([], [(-2, 1)]),
        ([], [(0, 256)]),
        ([], [(0, True)]),
    ],
)
def test_root_and_override_indices_and_bytes_are_adapter_validated(roots, overrides):
    with pytest.raises(ValueError):
        choose_bone_build_selection(
            SavedSelection((), (), 0, False), P, 1, roots, overrides
        )


@pytest.mark.parametrize(
    "selection",
    [
        SavedSelection(((float("nan"), 0, 0),), (2,), 0, False),
        SavedSelection(P, (1, 256), 0, True),
        SavedSelection(P, (1, 2), float("inf"), False),
        SavedSelection(P, (1, 2), 0, cast(bool, 1)),
    ],
)
def test_valid_shape_does_not_bypass_finite_byte_bool_adapter_policy(selection):
    assert selection_is_valid(selection)
    with pytest.raises(ValueError):
        choose_bone_build_selection(selection, (), 0, (), ())


def test_proxy_radius_and_grid_multiplier_are_actual_rip_constants():
    result = proxy_selection_search_parameters(0.25, 0.5)
    assert result.radius == 0.5 and result.grid_size == 0.75
    assert proxy_selection_search_parameters(2, 1).radius == 2
    tiny = proxy_selection_search_parameters(-5, -1)
    assert struct.pack("<f", tiny.radius).hex() == "acc52737"
    assert (
        tiny.grid_size == struct.unpack("<f", struct.pack("<f", tiny.radius * 1.5))[0]
    )
    # ConvertFrom uses target-AABB * 0.2 and radius * 0.5: DIFFERENT contract.


@pytest.mark.parametrize(
    "average,maximum", [(float("nan"), 1), (1, float("inf")), (1e39, 1), (True, 1)]
)
def test_nonfinite_search_adapter_rejection(average, maximum):
    with pytest.raises(ValueError):
        proxy_selection_search_parameters(average, maximum)


def test_proxy_attribute_kernel_ors_old_flags_preserves_no_match_and_invalid_winner():
    result = apply_proxy_selection_attributes(
        P, (128, 255), [(0, 0, 0)], (1,), 0.1, [(0,), ()]
    )
    assert result == (129, 255)
    assert apply_proxy_selection_attributes(
        [(0, 0, 0)], (130,), [(0, 0, 0)], (0,), 1, [(0,)]
    ) == (130,)


def test_proxy_kernel_inclusive_radius_and_later_ties_keep_all_flags():
    positions = [(-1, 0, 0), (1, 0, 0)]
    assert apply_proxy_selection_attributes(
        [(0, 0, 0)], (128,), positions, (1, 4), 1, [(0, 1)]
    ) == (132,)
    assert apply_proxy_selection_attributes(
        [(0, 0, 0)], (128,), positions, (1, 4), 1, [(1, 0)]
    ) == (129,)


def test_all_byte_pairs_preserve_original_or_contract():
    targets = [(0, 0, 0)] * 256
    candidates = [(0,)] * 256
    for winner in range(256):
        result = apply_proxy_selection_attributes(
            targets, tuple(range(256)), [(0, 0, 0)], (winner,), 0, candidates
        )
        assert result == tuple(old | winner for old in range(256))


@pytest.mark.parametrize("positions,old", [(P, (1,)), (P, (1, 256)), (P, (1, True))])
def test_proxy_old_attribute_adapter_rejection(positions, old):
    with pytest.raises(ValueError):
        apply_proxy_selection_attributes(positions, old, P, (1, 2), 1, [(0,), (1,)])


def test_fresh_grid_composition_uses_reverse_serial_ties_then_bone_flags():
    selection = SavedSelection(((0, 0, 0), (0, 0, 0)), (1, 2), 0.01, False)
    result = apply_bone_proxy_selection(
        [(0, 0, 0), (10, 0, 0)], (128, 2), (16, 32), selection, 0.02
    )
    # Head insertion [1,0] -> later index0 wins Fixed, not source index1.
    assert result.attributes == (129, 2)
    assert result.transform_flags == (26, 44)
    assert result.search == proxy_selection_search_parameters(0.02, 0.01)


def test_existing_move_bit_wins_flag_priority_even_when_nearest_source_is_fixed():
    result = apply_bone_proxy_selection(
        [(0, 0, 0)], (2,), (16,), SavedSelection(((0, 0, 0),), (1,), 1, True), 0
    )
    assert result.attributes == (3,) and result.transform_flags == (28,)


def test_apply_does_not_transform_or_match_bone_names_and_can_have_extra_saved_points():
    selection = SavedSelection(
        ((100, 0, 0), (100, 1, 0), (100, 2, 0)), (1, 2, 2), 1, False
    )
    result = apply_bone_proxy_selection(P, (128, 0), (16, 32), selection, 0.1)
    assert result.attributes == (128, 0) and result.transform_flags == (16, 32)


@pytest.mark.parametrize(
    "selection",
    [
        SavedSelection(None, None, 0, False),
        SavedSelection((), (), 0, False),
        SavedSelection(P, (1,), 0, False),
    ],
)
def test_apply_invalid_selection_is_explicit_error_not_empty_conversion_noop(selection):
    with pytest.raises(ValueError):
        apply_bone_proxy_selection(P, (0, 0), (0, 0), selection, 1)


def test_empty_proxy_with_valid_saved_selection_has_no_output():
    result = apply_bone_proxy_selection(
        (), (), (), SavedSelection(P, (1, 2), 1, False), 1
    )
    assert result.attributes == result.transform_flags == ()


def test_flags_must_be_parallel_even_if_matching_succeeds():
    with pytest.raises(ValueError):
        apply_bone_proxy_selection(
            P, (0, 0), (0,), SavedSelection(P, (1, 2), 1, False), 1
        )
