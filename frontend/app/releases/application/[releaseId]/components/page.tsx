import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Components = {
  release_id: string; version: string; base_release: { id: string; version: string } | null;
  components: { id: string; code: string | null; name: string | null; asr_version: string | null;
    declared_delta_type: string; base_component_version: string | null;
    base_link_status: 'VALID' | 'INVALID' | 'NOT_RECORDED' }[];
  unlinked_base_components: { id: string; code: string | null; name: string | null; version: string | null }[];
};

export default async function Page({ params }: { params: Promise<{ releaseId: string }> }) {
  const { releaseId } = await params;
  const base = `/releases/application/${encodeURIComponent(releaseId)}`;
  const data = await apiGet<Components>(`/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/components`);
  if (!data) return <section className="panel"><h1>Components unavailable</h1>
    <p className="muted">The application release was not found or the API could not be reached.</p>
    <Link href={base}>← Release profile</Link></section>;
  return <>
    <div className="top"><div><div className="eyebrow">APPLICATION RELEASE COMPONENTS</div><h1>ASR {data.version}</h1>
      <p className="muted">Declared component differences against {data.base_release ? `SSR ${data.base_release.version}` : 'an unrecorded SSR base'}.</p></div></div>
    <section className="panel tablewrap"><h2>ASR component declarations</h2>
      <p className="muted">A delta label is a recorded declaration. The SSR component version appears only when a matching base component link is stored.</p>
      <table><thead><tr><th>Component</th><th>ASR Version</th><th>Declared Delta</th><th>Linked SSR Version</th><th>Baseline Link</th></tr></thead>
        <tbody>{data.components.map(row => <tr key={row.id}>
          <td><b>{row.name || row.code || row.id}</b>{row.code && <><br />{row.code}</>}</td>
          <td>{row.asr_version || '—'}</td>
          <td><span className={'status ' + (row.declared_delta_type === 'UNCHANGED' ? 'pass' : 'warning')}>{row.declared_delta_type}</span></td>
          <td>{row.base_component_version || '—'}</td>
          <td>{row.base_link_status === 'VALID' ? 'Linked to base SSR' : row.base_link_status === 'INVALID' ? 'Invalid base link' : 'Not recorded'}</td>
        </tr>)}</tbody></table>{data.components.length === 0 && <p className="muted">No ASR components recorded.</p>}
    </section>
    {data.unlinked_base_components.length > 0 && <section className="panel tablewrap"><h2>SSR components without an ASR link</h2>
      <p className="muted">Their presence in the SSR does not establish whether the ASR inherits, changes or omits them.</p>
      <table><thead><tr><th>Component</th><th>SSR Version</th></tr></thead><tbody>
        {data.unlinked_base_components.map(row => <tr key={row.id}><td>{row.name || row.code || row.id}</td><td>{row.version || '—'}</td></tr>)}
      </tbody></table></section>}
    <p className="datasource"><Link href={base}>← Release profile</Link></p>
  </>;
}
