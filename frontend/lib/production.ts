export type ReleaseReference = {
  release_id: string | null;
  version: string | null;
  snapshot_id: string | null;
  snapshot_no: string | null;
};

export type ActualCorrection = {
  id: string;
  revision: number;
  actual: ReleaseReference | null;
  correction_reason: string;
  actor_name: string;
  deployed_at: string | null;
  recorded_at: string;
  audit_event_no: string;
};

export type ActualHistory = {
  history_state: string;
  recorded_baseline: {
    source: string;
    recorded_actual_version: number;
    actual: ReleaseReference | null;
    recorded_status: string;
    deployed_at: string | null;
    recorded_at: string;
  } | null;
  correction_count: number;
  corrections: ActualCorrection[];
};

export type DeploymentDetail = {
  id: string;
  deployment_no: string;
  status: string;
  actual_version?: number;
  authorization: { id: string; authorization_no: string; status: string } | null;
  customer: { id: string; code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  site: { id: string; site_code: string; name: string } | null;
  line: { id: string; line_code: string; name: string } | null;
  expected: ReleaseReference;
  actual: ReleaseReference | null;
  deployed_at: string | null;
  actual_history?: ActualHistory;
  changeovers: {
    id: string;
    changeover_no: string;
    from_version: string;
    to_version: string;
    status: string;
    changed_at: string | null;
    note: string | null;
    history_state?: string;
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
    history_state?: string;
  }[];
};

/** Bounded profile omits embedded history; catalogs remain the history source. */
export type DeploymentProfile = Omit<DeploymentDetail, 'changeovers' | 'batches'> & {
  software_observation: string;
  history_counts: { changeovers: number; batches: number };
  notice: string;
  provenance: {
    authorization: { authorization_no: string; status: string } | null;
    distribution: { distribution_no: string; status: string } | null;
    delivery: { package_no: string; revision: number; status: string; release_id: string; snapshot_id: string } | null;
  };
};
