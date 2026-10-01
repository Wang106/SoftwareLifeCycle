
import { Localized, LocalizedAttributes } from "../../../../../components/localized";
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
  if (!data) return <section className="panel"><h1><Localized>{"Components unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p>
    <Link href={base}><Localized>{"← Release profile"}</Localized></Link></section>;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"APPLICATION RELEASE COMPONENTS"}</Localized></div><h1><Localized>{"ASR "}</Localized><Localized>{data.version}</Localized></h1>
      <p className="muted"><Localized>{"Declared component differences against "}</Localized><Localized>{data.base_release ? `SSR ${data.base_release.version}` : 'an unrecorded SSR base'}</Localized><Localized>{"."}</Localized></p></div></div>
    <section className="panel tablewrap"><h2><Localized>{"ASR component declarations"}</Localized></h2>
      <p className="muted"><Localized>{"A delta label is a recorded declaration. The SSR component version appears only when a matching base component link is stored."}</Localized></p>
      <table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"ASR Version"}</Localized></th><th><Localized>{"Declared Delta"}</Localized></th><th><Localized>{"Linked SSR Version"}</Localized></th><th><Localized>{"Baseline Link"}</Localized></th></tr></thead>
        <tbody><Localized>{data.components.map(row => <tr key={row.id}>
          <td><b><Localized>{row.name || row.code || row.id}</Localized></b><Localized>{row.code && <><br /><Localized>{row.code}</Localized></>}</Localized></td>
          <td><Localized>{row.asr_version || '—'}</Localized></td>
          <td><span className={'status ' + (row.declared_delta_type === 'UNCHANGED' ? 'pass' : 'warning')}><Localized>{row.declared_delta_type}</Localized></span></td>
          <td><Localized>{row.base_component_version || '—'}</Localized></td>
          <td><Localized>{row.base_link_status === 'VALID' ? 'Linked to base SSR' : row.base_link_status === 'INVALID' ? 'Invalid base link' : 'Not recorded'}</Localized></td>
        </tr>)}</Localized></tbody></table><Localized>{data.components.length === 0 && <p className="muted"><Localized>{"No ASR components recorded."}</Localized></p>}</Localized>
    </section>
    <Localized>{data.unlinked_base_components.length > 0 && <section className="panel tablewrap"><h2><Localized>{"SSR components without an ASR link"}</Localized></h2>
      <p className="muted"><Localized>{"Their presence in the SSR does not establish whether the ASR inherits, changes or omits them."}</Localized></p>
      <table><thead><tr><th><Localized>{"Component"}</Localized></th><th><Localized>{"SSR Version"}</Localized></th></tr></thead><tbody>
        <Localized>{data.unlinked_base_components.map(row => <tr key={row.id}><td><Localized>{row.name || row.code || row.id}</Localized></td><td><Localized>{row.version || '—'}</Localized></td></tr>)}</Localized>
      </tbody></table></section>}</Localized>
    <p className="datasource"><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
