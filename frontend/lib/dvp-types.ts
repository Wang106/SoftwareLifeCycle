export type Execution = { execution_no: number; result: string; actual_result: string | null; executed_at: string; release_id: string; release_version: string | null; release_type: string | null; snapshot_id: string; snapshot_no: string | null; test_release_no: string | null; context_consistent: boolean };
export type ReleaseOption = { id: string; version: string; type: string };
export type Context = { mode: string; release: ReleaseOption | null; snapshot: { id: string; snapshot_no: string } | null };
