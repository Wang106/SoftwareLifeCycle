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
