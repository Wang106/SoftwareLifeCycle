
import { Localized, LocalizedAttributes } from "../../components/localized";
import Link from 'next/link';
import { apiGet } from '../../lib/api';

type ChangeRow = { id: string; request_no: string; title: string; source: string; scope: string; change_type: string; status: string };

export default async function Page() {
  const rows = await apiGet<ChangeRow[]>('/api/v1/changes');
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"CHANGE CONTROL"}</Localized></div><h1><Localized>{"Software Change Requests"}</Localized></h1>
      <p className="muted"><Localized>{"From approved requirement to verified software change and release traceability."}</Localized></p></div></div>
    <div className="summary"><div><b><Localized>{rows?.length ?? '—'}</Localized></b><span><Localized>{"Visible SCR"}</Localized></span></div>
      <div><b><Localized>{rows ? rows.filter(row => row.status.includes('TEST')).length : '—'}</Localized></b><span><Localized>{"In Verification"}</Localized></span></div>
      <div><b><Localized>{rows ? rows.filter(row => row.status.includes('READY')).length : '—'}</Localized></b><span><Localized>{"Ready for Release"}</Localized></span></div></div>
    <Localized>{rows ? <section className="panel tablewrap"><table><thead><tr><th><Localized>{"SCR"}</Localized></th><th><Localized>{"Title"}</Localized></th><th><Localized>{"Source"}</Localized></th><th><Localized>{"Scope"}</Localized></th><th><Localized>{"Type"}</Localized></th><th><Localized>{"Status"}</Localized></th></tr></thead>
      <tbody><Localized>{rows.map(row => <tr key={row.id}><td><Link href={`/changes/${encodeURIComponent(row.request_no)}`}><b><Localized>{row.request_no}</Localized></b></Link></td>
        <td><Localized>{row.title}</Localized></td><td><Localized>{row.source}</Localized></td><td><Localized>{row.scope}</Localized></td><td><Localized>{row.change_type}</Localized></td>
        <td><span className={'status ' + (row.status.includes('READY') || row.status === 'RELEASED' ? 'pass' : 'warning')}><Localized>{row.status.replaceAll('_', ' ')}</Localized></span></td>
      </tr>)}</Localized></tbody></table><Localized>{rows.length === 0 && <p className="muted"><Localized>{"No change requests recorded."}</Localized></p>}</Localized></section>
      : <p className="datasource"><Localized>{"Change request API unavailable. Records will load when the backend is connected."}</Localized></p>}</Localized>
  </>;
}
