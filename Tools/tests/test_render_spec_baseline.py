"""The seal guards evidence provenance, not shader equivalence or screenshot fit."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render_spec_baseline as seal


@pytest.fixture
def fixture(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/reading.md').write_text('Source reading, not a proof.\n', encoding='utf-8')
    (tmp_path / 'shader.hlsl').write_text('// Keywords: NORMALMAP\nfloat wet = max(rain, localWet);\n', encoding='utf-8')
    plan = {
        'schema': 1, 'baseline': 'test-v1', 'scope': 'offline source subset',
        'groups': [
            {'id': 'docs', 'root': 'project', 'patterns': ['docs/*.md'], 'role': 'reading'},
            {'id': 'source', 'root': 'project', 'patterns': ['*.hlsl'], 'role': 'primary-source'},
        ],
        'contracts': [{'id': 'weather', 'dimensions': {'formula': 'pending', 'producer': 'pending'},
                       'remaining': ['Producer is not known.']}],
        'anchors': [{'id': 'wet', 'root': 'project', 'path': 'shader.hlsl',
                     'literal': 'float wet = max(rain, localWet);', 'contract': 'weather'}],
    }
    return tmp_path, plan, {'project': tmp_path}


def test_snapshot_records_headers_and_does_not_approve_pending_contract(fixture):
    _, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    record = next(item for item in manifest['files'] if item['path'] == 'shader.hlsl')
    assert record['keywords'] == ['NORMALMAP']
    assert manifest['approval'] == 'evidence-only'
    result = seal.verify(manifest, roots)
    assert result['integrity_ok'] and not result['complete']
    assert result['pending'] == ['weather:formula', 'weather:producer']


def test_changed_document_is_detected(fixture):
    root, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    (root / 'docs/reading.md').write_text('Now claiming complete.\n', encoding='utf-8')
    assert 'changed:project:docs/reading.md' in seal.verify(manifest, roots)['errors']


def test_missing_source_is_detected(fixture):
    root, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    (root / 'shader.hlsl').unlink()
    assert 'missing:project:shader.hlsl' in seal.verify(manifest, roots)['errors']


def test_new_document_requires_a_new_snapshot(fixture):
    root, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    (root / 'docs/other.md').write_text('New evidence.\n', encoding='utf-8')
    assert 'inventory:docs' in seal.verify(manifest, roots)['errors']


def test_relocation_preserves_relative_identity_and_digest(fixture, tmp_path):
    root, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    moved = tmp_path / 'relocated'
    moved.mkdir()
    (moved / 'docs').mkdir()
    (moved / 'docs/reading.md').write_bytes((root / 'docs/reading.md').read_bytes())
    (moved / 'shader.hlsl').write_bytes((root / 'shader.hlsl').read_bytes())
    assert seal.verify(manifest, {'project': moved})['integrity_ok']
    assert seal.snapshot(plan, {'project': moved})['digest'] == manifest['digest']


def test_manifest_tampering_is_detected(fixture):
    _, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    manifest['contracts'][0]['dimensions']['formula'] = 'verified'
    assert 'manifest-digest' in seal.verify(manifest, roots)['errors']


def test_anchor_change_is_not_hidden_by_recomputing_file_digest(fixture):
    root, plan, roots = fixture
    manifest = seal.snapshot(plan, roots)
    (root / 'shader.hlsl').write_text('float wet = rain;\n', encoding='utf-8')
    for record in manifest['files']:
        if record['path'] == 'shader.hlsl':
            record.update(seal.file_record(root / 'shader.hlsl', 'project', root))
    manifest['digest'] = seal.digest_payload(manifest)
    assert 'anchor:wet' in seal.verify(manifest, roots)['errors']


def test_complete_requires_every_dimension_and_no_remaining_questions(fixture):
    _, plan, roots = fixture
    plan['contracts'][0]['dimensions'] = {'formula': 'verified', 'producer': 'not-applicable'}
    manifest = seal.snapshot(plan, roots)
    assert not seal.verify(manifest, roots)['complete']
    plan['contracts'][0]['remaining'] = []
    manifest = seal.snapshot(plan, roots)
    assert seal.verify(manifest, roots)['complete']
    assert manifest['approval'] == 'evidence-only'  # The tool never issues semantic certification.


@pytest.mark.parametrize('path', ['../shader.hlsl', '/shader.hlsl', 'C:/shader.hlsl', '..\\shader.hlsl'])
def test_outside_root_is_rejected(fixture, path):
    _, _, roots = fixture
    with pytest.raises(ValueError):
        seal.resolve_path(roots, 'project', path)


def test_absolute_external_file_is_rejected(fixture, tmp_path):
    _, _, roots = fixture
    # Root itself exists; a resolved child outside it is not permitted.
    outside = tmp_path.parent / 'source-outside.hlsl'
    with pytest.raises(ValueError):
        seal.resolve_path(roots, 'project', str(outside))


@pytest.mark.parametrize('mutation', ['status', 'duplicate', 'unknown-contract', 'empty-dimensions', 'empty-contracts'])
def test_invalid_plan_fails_closed(fixture, mutation):
    _, plan, roots = fixture
    if mutation == 'status':
        plan['contracts'][0]['dimensions']['formula'] = 'probably'
    elif mutation == 'duplicate':
        plan['contracts'].append(copy.deepcopy(plan['contracts'][0]))
    elif mutation == 'unknown-contract':
        plan['anchors'][0]['contract'] = 'invented'
    elif mutation == 'empty-dimensions':
        plan['contracts'][0]['dimensions'] = {}
    else:
        plan['contracts'] = []
    with pytest.raises(ValueError):
        seal.snapshot(plan, roots)


def test_empty_inventory_and_missing_anchor_are_errors(fixture):
    _, plan, roots = fixture
    plan['groups'][0]['patterns'] = ['does-not-exist/*.md']
    with pytest.raises(ValueError, match='Empty'):
        seal.snapshot(plan, roots)
    plan['groups'][0]['patterns'] = ['docs/*.md']
    plan['anchors'][0]['literal'] = 'not in source'
    with pytest.raises(ValueError, match='anchor'):
        seal.snapshot(plan, roots)


def test_snapshot_refuses_overwrite_and_verify_cli_distinguishes_pending(fixture, capsys):
    root, plan, _ = fixture
    plan_path = root / 'plan.json'
    plan_path.write_text(json.dumps(plan), encoding='utf-8')
    output = root / 'snapshot.json'
    common = ['--project-root', str(root)]
    assert seal.main(['snapshot', str(plan_path), str(output)] + common) == 0
    with pytest.raises(FileExistsError):
        seal.main(['snapshot', str(plan_path), str(output)] + common)
    assert seal.main(['verify', str(output)] + common) == 0
    assert seal.main(['verify', str(output), '--require-complete'] + common) == 2
    (root / 'shader.hlsl').write_text('changed', encoding='utf-8')
    assert seal.main(['verify', str(output)] + common) == 1
    assert 'integrity_ok' in capsys.readouterr().out


def test_missing_root_and_duplicate_group_are_rejected(fixture):
    _, plan, roots = fixture
    with pytest.raises(ValueError, match='Unknown root'):
        seal.resolve_path(roots, 'absent', 'shader.hlsl')
    plan['groups'].append(copy.deepcopy(plan['groups'][0]))
    with pytest.raises(ValueError):
        seal.snapshot(plan, roots)
