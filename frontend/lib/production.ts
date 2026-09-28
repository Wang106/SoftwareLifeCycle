export type ReleaseReference = {
  release_id: string | null;
  version: string | null;
  snapshot_id: string | null;
  snapshot_no: string | null;
};

export type DeploymentDetail = {
  id: string;
  deployment_no: string;
  status: string;
  authorization: { id: string; authorization_no: string; status: string } | null;
  customer: { id: string; code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  site: { id: string; site_code: string; name: string } | null;
  line: { id: string; line_code: string; name: string } | null;
  expected: ReleaseReference;
  actual: ReleaseReference | null;
  deployed_at: string | null;
  changeovers: {
    id: string;
    changeover_no: string;
    from_version: string;
    to_version: string;
    status: string;
    changed_at: string | null;
    note: string | null;
  }[];
  batches: {
    id: string;
    batch_no: string;
    status: string;
    release_version: string;
    snapshot_no: string;
    started_at: string | null;
    ended_at: string | null;
    note: string | null;
  }[];
};

export const deploymentFallback: DeploymentDetail = {
  id: 'demo-deployment',
  deployment_no: 'DEP-0081',
  status: 'MATCH',
  authorization: { id: 'demo-authorization', authorization_no: 'PA-0081', status: 'APPROVED' },
  customer: { id: 'demo-customer', code: 'CUS-001', name: 'Customer A' },
  project: { id: 'demo-project', code: 'PRJ-X', name: 'Project X' },
  site: { id: 'demo-site', site_code: 'FACTORY-A', name: 'Factory A' },
  line: { id: 'demo-line', line_code: 'LINE-2', name: 'Line 2' },
  expected: { release_id: 'demo-release', version: '2.3.4', snapshot_id: 'demo-snapshot', snapshot_no: 'SNAP-008' },
  actual: { release_id: 'demo-release', version: '2.3.4', snapshot_id: 'demo-snapshot', snapshot_no: 'SNAP-008' },
  deployed_at: '2026-09-28T00:00:00Z',
  changeovers: [{ id: 'demo-changeover', changeover_no: 'CO-0032', from_version: '2.3.3', to_version: '2.3.4', status: 'COMPLETED', changed_at: '2026-09-28T00:00:00Z', note: 'Controlled software changeover.' }],
  batches: [{ id: 'demo-batch', batch_no: 'PB-1005-A', status: 'ACTIVE', release_version: '2.3.4', snapshot_no: 'SNAP-008', started_at: '2026-09-28T00:00:00Z', ended_at: null, note: 'Initial controlled production batch.' }],
};
