export type ChangeSummary = {
  id: string; request_no: string; title: string; source: string; scope: string; change_type: string;
  status: string; background: string | null; requirement: string | null; created_at: string;
  software: { code: string; name: string } | null; customer: { code: string; name: string } | null;
  project: { id: string; code: string; name: string } | null;
  criterion_count: number; issue_count: number; point_count: number; plan_count: number;
  point_item_count: number; plan_item_count: number;
};
export type ChangeSearch = Record<string, string | string[] | undefined>;
