export type CoverageSearch = Record<string, string | string[] | undefined>;
export type CoveragePins = { change_id: string; request_no: string; release_id: string; snapshot_id: string };
export type CoverageCount = { total: number; assigned: number; assignment_percent: number | null; passed: number | null };
export type CoverageSummary = CoveragePins & {
  basis: string; release: { id: string; type: string; version: string } | null;
  snapshot: { id: string; snapshot_no: string; number: number } | null;
  candidate_count: number; gap_count: number;
  summary: { acceptance: CoverageCount; change_points: CoverageCount; issues: CoverageCount;
    dvp: { total: number; executed: number | null; passed: number | null } };
};
export type CoverageRow = { id: string; ref?: string; description?: string; verification?: string;
  item_count?: number; excluded_link_count?: number; group_id?: string; assignment_count?: number;
  type?: string; version?: string; status?: string; code?: string; message?: string; owner_id?: string; kind?: string;
  item_no?: string; title?: string; scope?: string; declared_status?: string; execution_no?: number | null;
  result?: string | null; actual_result?: string | null; executed_at?: string | null;
  dvp_item_id?: string; actor_name?: string; reason?: string; created_at?: string;
  action?: 'ASSIGN'|'SUPERSEDE'|'WITHDRAW'; supersedes_id?: string|null;
  superseded_by_id?: string|null; effective?: boolean };
export type CoveragePage = CoveragePins & {kind?: string; group_id?: string;total:number;next_offset:number|null;items:CoverageRow[]};
export type SelectedCoverage = CoveragePins & CoverageRow & {kind:string;group_id:string;assignment_count:number};
export const rawCoverage = (search:CoverageSearch,key:string) => search[key] === undefined ? undefined : typeof search[key] === 'string' ? search[key] as string : 'invalid';
export function matchingCoverage<T extends CoveragePins>(value:T|null,data:CoveragePins):value is T { return !!value && value.change_id === data.change_id && value.request_no === data.request_no && value.release_id === data.release_id && value.snapshot_id === data.snapshot_id; }
