import CommandWorkbench from '../../components/command-workbench';
import { Operation } from '../../lib/command-draft';

export const dynamic = 'force-dynamic';
export default async function Page({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const operation: Operation = query.operation === 'actual' || query.operation === 'batch' || query.operation === 'approval' || query.operation === 'decision' ? query.operation : 'snapshot';
  const target = typeof query.target === 'string' ? query.target.slice(0, 80) : '';
  const step = typeof query.step === 'string' && query.step.length <= 36 ? query.step : '';
  return <>
    <div className="top"><div><div className="eyebrow">CONTROLLED COMMANDS</div><h1>Prepare a lifecycle request</h1>
      <p className="muted">Validate, review and copy a Snapshot, actual-software, Batch, approval action or release decision request for your controlled API client.</p></div></div>
    <CommandWorkbench key={`${operation}:${target}:${step}`} initialOperation={operation} initialTarget={target} initialStep={step} />
  </>;
}
