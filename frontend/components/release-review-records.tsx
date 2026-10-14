import Link from 'next/link';
import { apiGet } from '../lib/api';
import { Localized } from './localized';
import type { ReleaseSearch } from './release-catalog';
type Approval = {
    id: string;
    approval_no: string;
    target_type: string;
    target_id: string;
    status: string;
    submitted_by: string | null;
    submitted_at: string | null;
    step_count: number;
    action_count: number;
    release: {
        id: string;
    } | null;
    snapshot: {
        id: string;
        snapshot_no: string;
    } | null;
};
type ApprovalPage = {
    total: number;
    next_offset: number | null;
    items: Approval[];
};
type Snapshot = {
    id: string;
    release_id: string;
    snapshot_no: string;
    is_current_snapshot: boolean;
};
type SnapshotHistory = {
    release: {
        id: string;
        type: string;
    };
    total: number;
    items: Snapshot[];
};
type Artifact = {
    id: string;
    filename: string;
    component_code: string;
    component_version: string;
    artifact_type: string;
    sha256: string;
};
type ArtifactPage = {
    release_id: string;
    snapshot_id: string;
    snapshot_no: string;
    total: number;
    next_offset: number | null;
    items: Artifact[];
};
export async function ReleaseReviewRecords({ releaseId, kind, search }: {
    releaseId: string;
    kind: 'standard' | 'application';
    search: ReleaseSearch;
}) {
    const queryValue = (key: string) => typeof search[key] === 'string' ? search[key] as string : 'invalid';
    const pageLink = (updates: Record<string, string>) => {
        const q = new URLSearchParams();
        for (const [key, val] of Object.entries(search))
            if (val !== undefined)
                q.set(key, typeof val === 'string' ? val : 'invalid');
        for (const [key, val] of Object.entries(updates))
            q.set(key, val);
        return `/releases/${kind}/${encodeURIComponent(releaseId)}?${q}`;
    };
    const paging = (key: string, next: number | null, pins: Record<string, string> = {}) => <Localized><p><Link href={pageLink({ ...pins, [key]: '0' })}><Localized>{"First page"}</Localized></Link> {next !== null && <Link href={pageLink({ ...pins, [key]: String(next) })}><Localized>{"Next page →"}</Localized></Link>}</p></Localized>;
    const approvalQuery = new URLSearchParams({ release_id: releaseId, limit: '20' });
    if (search.approval_offset !== undefined)
        approvalQuery.set('offset', queryValue('approval_offset'));
    const approvalsPromise = apiGet<ApprovalPage>(`/api/v1/governance/approvals?${approvalQuery}`);
    let snapshot: Snapshot | null = null, files: ArtifactPage | null = null, noSnapshot = false;
    if (kind === 'standard') {
        let selected: {
            id: string;
            snapshot_no: string;
        } | null = null;
        if (search.files_snapshot_no !== undefined || search.files_snapshot_id !== undefined) {
            if (typeof search.files_snapshot_no === 'string' && typeof search.files_snapshot_id === 'string')
                selected = { id: search.files_snapshot_id, snapshot_no: search.files_snapshot_no };
        }
        else {
            const history = await apiGet<SnapshotHistory>(`/api/v1/releases/${encodeURIComponent(releaseId)}/snapshots?limit=1`);
            if (history?.release.id === releaseId && history.release.type === 'STANDARD') {
                selected = history.items[0] ?? null;
                noSnapshot = history.total === 0 && history.items.length === 0;
            }
        }
        if (selected) {
            const summary = await apiGet<Snapshot>(`/api/v1/snapshots/${encodeURIComponent(selected.snapshot_no)}/summary`);
            if (summary?.release_id === releaseId && summary.id === selected.id && summary.snapshot_no === selected.snapshot_no) {
                snapshot = summary;
                const q = new URLSearchParams({ snapshot_id: snapshot.id, limit: '20' });
                if (search.files_offset !== undefined)
                    q.set('offset', queryValue('files_offset'));
                const page = await apiGet<ArtifactPage>(`/api/v1/snapshots/${encodeURIComponent(snapshot.snapshot_no)}/artifacts?${q}`);
                files = page?.release_id === releaseId && page.snapshot_id === snapshot.id && page.snapshot_no === snapshot.snapshot_no ? page : null;
            }
        }
    }
    const response = await approvalsPromise;
    const approvals = response && response.items.every(row => row.target_type === 'RELEASE' && row.target_id === releaseId && (!row.release || row.release.id === releaseId)) ? response : null;
    return <Localized>
    {kind === 'standard' && <section className="panel release-record-table"><h2><Localized>{"Software files"}</Localized></h2>
      {files && snapshot ? <><p><Link href={`/snapshots/${encodeURIComponent(snapshot.snapshot_no)}?${new URLSearchParams({ manifest_snapshot_id: snapshot.id })}`}>{snapshot.snapshot_no}</Link><Localized>{"·"}</Localized><Localized>{snapshot.is_current_snapshot ? 'Current snapshot' : 'Historical snapshot'}</Localized></p>
        <table><thead><tr><th><Localized>{"Filename"}</Localized></th><th><Localized>{"Component"}</Localized></th><th><Localized>{"Version"}</Localized></th><th><Localized>{"Artifact type"}</Localized></th><th><Localized>{"SHA-256"}</Localized></th></tr></thead><tbody>{files.items.map(row => <tr key={row.id}><td>{row.filename}</td><td>{row.component_code}</td><td>{row.component_version}</td><td>{row.artifact_type}</td><td><code className="file-hash">{row.sha256}</code></td></tr>)}</tbody></table>
        <p><Localized>{"Total files: "}</Localized>{files.total}</p>{!files.items.length && <p className="muted"><Localized>{"No software files on this page."}</Localized></p>}{paging('files_offset', files.next_offset, { files_snapshot_id: snapshot.id, files_snapshot_no: snapshot.snapshot_no })}</>
                : <p className="muted"><Localized>{noSnapshot ? 'No snapshot is available for software files.' : 'Software files unavailable.'}</Localized></p>}
    </section>}
    <section className="panel release-record-table"><h2><Localized>{"Approval records"}</Localized></h2>
      {approvals ? <><p><Localized>{"Recorded count: "}</Localized>{approvals.total}</p><table><thead><tr><th><Localized>{"Approval"}</Localized></th><th><Localized>{"Status "}</Localized></th><th><Localized>{"Snapshot"}</Localized></th><th><Localized>{"Submitted by"}</Localized></th><th><Localized>{"Submitted at"}</Localized></th><th><Localized>{"Steps"}</Localized></th><th><Localized>{"Actions"}</Localized></th></tr></thead><tbody>{approvals.items.map(row => <tr key={row.id}><td><Link href={`/approvals/${encodeURIComponent(row.approval_no)}`}>{row.approval_no}</Link></td><td><Localized>{row.status}</Localized></td><td>{row.snapshot ? <Link href={`/snapshots/${encodeURIComponent(row.snapshot.snapshot_no)}?${new URLSearchParams({ manifest_snapshot_id: row.snapshot.id })}`}>{row.snapshot.snapshot_no}</Link> : '—'}</td><td>{row.submitted_by ?? '—'}</td><td>{row.submitted_at ?? '—'}</td><td>{row.step_count}</td><td>{row.action_count}</td></tr>)}</tbody></table>
        {!approvals.items.length && <p className="muted"><Localized>{"No approval records on this page."}</Localized></p>}{paging('approval_offset', approvals.next_offset)}</>
            : <p className="muted"><Localized>{"Approval records unavailable."}</Localized></p>}
    </section>
  </Localized>;
}
