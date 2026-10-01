import CommandWorkbench from '../../components/command-workbench';
import { Operation } from '../../lib/command-draft';

export const dynamic = 'force-dynamic';
export default async function Page({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const operation: Operation = query.operation === 'actual' || query.operation === 'batch' ? query.operation : 'snapshot';
  const target = typeof query.target === 'string' ? query.target.slice(0, 80) : '';
  return <>
    <div className="top"><div><div className="eyebrow">CONTROLLED COMMANDS</div><h1>Prepare a lifecycle request</h1>
      <p className="muted">Validate, review and copy a Snapshot, actual-software or Batch request for your controlled API client.</p></div></div>
    <CommandWorkbench key={`${operation}:${target}`} initialOperation={operation} initialTarget={target} />
  </>;
}
