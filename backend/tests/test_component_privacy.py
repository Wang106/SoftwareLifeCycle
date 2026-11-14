"""Public projections must not observe private declarations or their artifacts."""
import uuid
import pytest
from test_application_release_creation import creation_db
from app.models.audit import AuditEvent
from app.models.core import Release, ApplicationReleaseDetail, ReleaseComponent, ComponentDefinition, Artifact
from app.api.asr_components import component_summary, component_declarations, unlinked_base_components, ComponentPage, SummarySelection
from app.services.ssr_asr_aggregation import ssr_asr_aggregated_differences
from app.services.artifact_policy import ArtifactPolicyService
from app.api.search import _artifact_results
from app.services.snapshot import SnapshotService, SnapshotError


def setup(db, ids):
    definition = ComponentDefinition(code='PRIVACY', name='Historical component')
    release = Release(software_id=ids['software'], release_type='APPLICATION', version='privacy')
    db.add_all([definition, release]); db.flush()
    db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=ids['customer'], project_id=ids['project'], standard_base_release_id=ids['standard']))
    base = ReleaseComponent(release_id=ids['standard'], component_definition_id=definition.id, version='base')
    legacy = ReleaseComponent(release_id=release.id, component_definition_id=definition.id, version='legacy', delta_type='ADDED')
    db.add_all([base, legacy]); db.commit()
    return release, base, legacy


def mark(db, row, mode):
    db.add(AuditEvent(event_no=('eVt-AsRc-' if mode == 'prefix' else 'OTHER-') + row.id.hex,
        event_type='APPLICATION_COMPONENT_DECLARED' if mode == 'type' else 'MALFORMED',
        entity_id=row.id, entity_type='MALFORMED', entity_ref='malformed', action='MALFORMED',
        actor_name='Synthetic', summary='Private', payload_json={'malformed': True}))


def projections(db, release, ids):
    return [component_summary(release.id, SummarySelection(), db),
        component_declarations(release.id, ComponentPage(limit=1), db),
        component_declarations(release.id, ComponentPage(limit=1, offset=1), db),
        unlinked_base_components(release.id, ComponentPage(), db),
        ssr_asr_aggregated_differences(db, ids['standard'])]


@pytest.mark.parametrize('mode', ['prefix', 'type'])
def test_private_declarations_leave_public_aliases_counts_and_pages_unchanged(creation_db, mode):
    db, ids = creation_db
    release, base, legacy = setup(db, ids)
    before = projections(db, release, ids)
    for version, link in [('secret-1', base.id), ('secret-2', base.id), ('secret-3', None)]:
        row = ReleaseComponent(release_id=release.id, component_definition_id=base.component_definition_id,
            version=version, base_component_id=link, delta_type='MODIFIED')
        db.add(row); db.flush(); mark(db, row, mode)
    db.commit()
    assert projections(db, release, ids) == before


def artifact(db, component, filename):
    row = Artifact(release_component_id=component.id, artifact_type='BIN', filename=filename,
        storage_reference='synthetic-only', sha256='a'*64, controlled=False,
        classification='INTERNAL', distribution_level='INTERNAL_ONLY', ai_access_policy='DENY')
    db.add(row); db.flush(); return row


@pytest.mark.parametrize('mode', ['prefix', 'type'])
def test_private_artifacts_hidden_and_snapshot_fails_without_partial_evidence(creation_db, mode):
    db, ids = creation_db
    release, base, legacy = setup(db, ids)
    public_artifact = artifact(db, legacy, 'public.bin'); db.commit()
    policy = ArtifactPolicyService(db)
    before = policy.summarize_release(release.id).as_dict()
    private = ReleaseComponent(release_id=release.id, component_definition_id=base.component_definition_id, version='secret')
    db.add(private); db.flush(); mark(db, private, mode)
    artifact(db, private, 'secret.bin'); db.commit()
    assert policy.summarize_release(release.id).as_dict() == before
    assert [row.id for row in policy.release_artifacts(release.id)] == [public_artifact.id]
    assert _artifact_results(db, '%secret%', 10) == []
    assert len(_artifact_results(db, '%public%', 10)) == 1
    with pytest.raises(SnapshotError, match='Private component artifacts'):
        SnapshotService().create(db, release.id)
    from sqlalchemy import select, func
    from app.models.snapshot import ReleaseSnapshot, SnapshotArtifact
    assert db.scalar(select(func.count()).select_from(ReleaseSnapshot)) == 0
    assert db.scalar(select(func.count()).select_from(SnapshotArtifact)) == 0


def test_marker_matches_only_exact_component_and_base_alias_is_hidden(creation_db):
    db, ids = creation_db
    release, base, legacy = setup(db, ids)
    # An unrelated audit row must not hide ordinary sample components.
    unrelated = ReleaseComponent(id=uuid.uuid4())
    mark(db, unrelated, 'type'); db.commit()
    assert component_summary(release.id, SummarySelection(), db)['component_count'] == 1
    # Defensive handling for any private marker on a baseline row: both the
    # baseline anti-join and declaration's aliased base projection must hide it.
    legacy.base_component_id = base.id
    mark(db, base, 'prefix'); db.commit()
    item = component_declarations(release.id, ComponentPage(), db)['items'][0]
    assert item['base_component_version'] is None and item['base_link_status'] == 'INVALID'
    assert unlinked_base_components(release.id, ComponentPage(), db)['total'] == 0
    aggregate = ssr_asr_aggregated_differences(db, ids['standard'])
    assert aggregate['delta_type_aggregate']['by_delta_type']['ADDED']['INVALID'] == 1
    assert aggregate['unlinked_base_aggregate']['baseline_component_count'] == 0


@pytest.mark.parametrize('authorization', [None, 'Bearer synthetic-ignored-on-public-reads'])
def test_public_http_projections_never_include_private_rows(creation_db, authorization):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.db import get_db
    db, ids = creation_db
    release, base, legacy = setup(db, ids)
    paths = [f'/api/v1/releases/application/id/{release.id}/components/{suffix}'
             for suffix in ['summary', 'declarations?limit=1', 'unlinked-base']]
    paths.append(f'/api/v1/releases/standard/id/{ids["standard"]}/aggregated-differences')
    old = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            headers = {'Authorization': authorization} if authorization else {}
            before = [client.get(path, headers=headers) for path in paths]
            assert all(response.status_code == 200 for response in before)
            private = ReleaseComponent(release_id=release.id, component_definition_id=base.component_definition_id,
                version='secret-http', base_component_id=base.id)
            db.add(private); db.flush(); mark(db, private, 'type'); db.commit()
            after = [client.get(path, headers=headers) for path in paths]
            assert all(response.status_code == 200 for response in after)
            assert [response.json() for response in before] == [response.json() for response in after]
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(old)
