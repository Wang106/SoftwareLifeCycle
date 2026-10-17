import Link from 'next/link';
import {apiGet} from '../../../lib/api';
import {inspectDemoStatus} from '../../../lib/demo-status';
import {Localized} from '../../../components/localized';

export const dynamic = 'force-dynamic';
const labels = {
  confirmed: 'Confirmed for this data check',
  unavailable: 'Not confirmed: endpoint unavailable',
  invalid: 'Not confirmed: unexpected response',
  incomplete: 'Not confirmed: not ready or incomplete',
  mismatch: 'Not confirmed: API contract mismatch',
};

export default async function Page() {
  const observedAt = new Date().toISOString();
  const [health, excel, evidence] = await Promise.all([
    apiGet<unknown>('/health/ready', {timeoutMs: 10000}),
    apiGet<unknown>('/api/v1/demo/zfi-import', {timeoutMs: 10000}),
    apiGet<unknown>('/api/v1/demo/release-evidence', {timeoutMs: 10000}),
  ]);
  const result = inspectDemoStatus(health, excel, evidence);
  return <Localized>
    <div className="top"><div><h1><Localized>{'Demonstration status'}</Localized></h1>
      <p className="muted"><Localized>{'Read-only status of the API and sample data used by this frontend. Select Read again to refresh.'}</Localized></p></div></div>
    <p><Link href="/demo/zfi"><Localized>{'Excel demonstration overview'}</Localized></Link> <Localized>{' · '}</Localized>
      <Link href="/demo/releases"><Localized>{'Release evidence demonstration'}</Localized></Link> <Localized>{' · '}</Localized>
      <a href="/demo/status"><Localized>{'Read again'}</Localized></a></p>
    <section className="panel">
      <h2><Localized>{result.allConfirmed ? 'Demonstration data checks confirmed' : 'Demonstration data checks not confirmed'}</Localized></h2>
      <p className="muted"><Localized>{'These data checks do not establish real browser acceptance, real personnel approval or a formal release.'}</Localized></p>
      <p><Localized>{'Observed at (UTC)'}</Localized>: <time dateTime={observedAt}>{observedAt}</time></p>
      <p className="muted"><Localized>{'These observations may change as data changes. Read again for a new observation.'}</Localized></p>
    </section>
    <div className="grid2">
      <section className="panel">
        <h2><Localized>{'API readiness check'}</Localized></h2>
        <p><span className={result.api.state === 'confirmed' ? 'status pass' : 'status warning'}><Localized>{labels[result.api.state]}</Localized></span></p>
        <dl>
          <dt><Localized>{'Observed API version'}</Localized></dt><dd>{result.api.version || <Localized>{'Not recorded'}</Localized>}</dd>
          <dt><Localized>{'Required API version'}</Localized></dt><dd>{result.api.expectedVersion}</dd>
          <dt><Localized>{'Observed database revision'}</Localized></dt><dd className="demo-status-value">{result.api.revision || <Localized>{'Not recorded'}</Localized>}</dd>
          <dt><Localized>{'Required database revision'}</Localized></dt><dd className="demo-status-value">{result.api.expectedRevision}</dd>
        </dl>
        <p className="muted"><Localized>{'API readiness is not release readiness.'}</Localized></p>
        <p className="muted"><Localized>{'An unavailable endpoint does not identify whether configuration, network or database readiness caused the missing response.'}</Localized></p>
      </section>
      <section className="panel">
        <h2><Localized>{'Excel sample family check'}</Localized></h2>
        <p><span className={result.excel.state === 'confirmed' ? 'status pass' : 'status warning'}><Localized>{labels[result.excel.state]}</Localized></span></p>
        <p><Localized>{'Expected records'}</Localized>: {result.excel.expectedRecords} <Localized>{' · '}</Localized>
          <Localized>{'Observed records'}</Localized>: {result.excel.records ?? <Localized>{'Not recorded'}</Localized>}</p>
        {result.excel.records !== null && <p>SSR: {result.excel.standard} <Localized>{' · '}</Localized> ASR: {result.excel.application}</p>}
        <p className="muted"><Localized>{'The import marker, exact release identities and original approval references are checked. Missing firmware and tests are not created.'}</Localized></p>
      </section>
      <section className="panel">
        <h2><Localized>{'Independent release evidence family check'}</Localized></h2>
        <p><span className={result.evidence.state === 'confirmed' ? 'status pass' : 'status warning'}><Localized>{labels[result.evidence.state]}</Localized></span></p>
        <p><Localized>{'Expected records'}</Localized>: {result.evidence.expectedRecords} <Localized>{' · '}</Localized>
          <Localized>{'Observed records'}</Localized>: {result.evidence.records ?? <Localized>{'Not recorded'}</Localized>}</p>
        <p className="muted"><Localized>{'This synthetic family is checked separately. It does not supply missing test evidence for Excel records.'}</Localized></p>
      </section>
    </div>
  </Localized>;
}
