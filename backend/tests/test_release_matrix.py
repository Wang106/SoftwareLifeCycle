import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.api.release_matrix import release_matrix
from app.models.core import ApplicationReleaseDetail, Customer, Project, Release, SoftwareProduct, Supplier
from app.models.snapshot import ReleaseSnapshot


@pytest.fixture
def matrix_db():
    metadata = MetaData()
    for model in (Supplier, Customer, Project, SoftwareProduct, Release, ApplicationReleaseDetail, ReleaseSnapshot):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    engine = create_engine('sqlite://')
    metadata.create_all(engine)
    with Session(engine) as db:
        supplier = Supplier(id=uuid.uuid4(), code='SUP', name='Supplier')
        customers = [Customer(id=uuid.uuid4(), code='A', name='Percent%Co', region='APAC'),
                     Customer(id=uuid.uuid4(), code='B', name='Europe Co', region='EUROPE'),
                     Customer(id=uuid.uuid4(), code='C', name='No projects')]
        projects = [Project(id=uuid.uuid4(), customer_id=c.id, project_code='SHARED', name=f'Project {c.code}')
                    for c in customers[:2]]
        product = SoftwareProduct(id=uuid.uuid4(), supplier_id=supplier.id, code='BMS', name='Battery software')
        base = Release(id=uuid.uuid4(), software_id=product.id, release_type='STANDARD', version='5.1', status='RELEASED')
        versions = [Release(id=uuid.uuid4(), software_id=product.id, release_type='APPLICATION',
            version=version, status=status, created_at=datetime(2026, 9, day, tzinfo=timezone.utc))
            for version, status, day in [('1.0', 'RELEASED', 28), ('2.0', 'DRAFT', 29)]]
        db.add_all([supplier, *customers, *projects, product, base, *versions])
        db.flush()
        for release in versions:
            db.add(ApplicationReleaseDetail(release_id=release.id, customer_id=customers[0].id,
                project_id=projects[0].id, standard_base_release_id=base.id))
        for number in [1, 2]:
            db.add(ReleaseSnapshot(id=uuid.uuid4(), snapshot_no=f'SNAP-{number}',
                release_id=versions[1].id, snapshot_number=number, content_hash='a' * 64))
        db.commit()
        yield db, customers, projects, versions
    engine.dispose()


def query(db, **filters):
    args = dict(region=None, customer=None, project_id=None, status=None, q=None, limit=50, offset=0)
    args.update(filters)
    return release_matrix(db=db, **args)


def test_matrix_keeps_release_history_and_empty_organization_contexts(matrix_db):
    db, _, _, versions = matrix_db
    result = query(db)
    assert result['summary'] == {'customers': 3, 'projects': 2, 'application_releases': 2}
    assert result['total'] == 4
    assert [row['application_release']['version'] for row in result['items'][:2]] == ['2.0', '1.0']
    assert result['items'][0]['standard_release']['version'] == '5.1'
    assert result['items'][0]['snapshot']['snapshot_no'] == 'SNAP-2'
    assert result['items'][1]['snapshot'] is None
    assert result['items'][2]['project'] is not None
    assert result['items'][2]['application_release'] is None
    assert result['items'][3]['project'] is None
    assert result['items'][3]['customer']['region'] == 'UNASSIGNED'
    assert result['next_offset'] is None


@pytest.mark.parametrize(('filters', 'codes'), [({'region': 'APAC'}, ['A', 'A']),
    ({'region': 'EUROPE'}, ['B']), ({'region': 'UNASSIGNED'}, ['C']),
    ({'customer': 'B'}, ['B']), ({'status': 'RELEASED'}, ['A']),
    ({'q': '%'}, ['A', 'A']), ({'q': '5.1'}, ['A', 'A']), ({'q': 'missing'}, [])])
def test_matrix_filters_execute_against_actual_sql(matrix_db, filters, codes):
    db, *_ = matrix_db
    result = query(db, **filters)
    assert [row['customer']['code'] for row in result['items']] == codes
    assert result['total'] == len(codes)


def test_project_filter_uses_uuid_not_duplicate_project_code(matrix_db):
    db, _, projects, _ = matrix_db
    result = query(db, project_id=projects[1].id)
    assert result['summary']['projects'] == 1
    assert result['items'][0]['customer']['code'] == 'B'


def test_pagination_has_global_filtered_summary_and_no_duplicate_snapshots(matrix_db):
    db, *_ = matrix_db
    first = query(db, limit=1)
    second = query(db, limit=1, offset=first['next_offset'])
    assert first['total'] == second['total'] == 4
    assert first['summary']['application_releases'] == 2
    assert first['items'][0]['application_release']['id'] != second['items'][0]['application_release']['id']
    assert query(db, offset=4)['items'] == []
    assert query(db, offset=4)['next_offset'] is None
