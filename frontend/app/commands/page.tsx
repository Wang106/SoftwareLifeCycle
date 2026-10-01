import CommandWorkbench from '../../components/command-workbench';
import { Operation, Fields, resourceTypes } from '../../lib/command-draft';

export const dynamic = 'force-dynamic';
export default async function Page({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const operation: Operation = query.operation === 'actual' || query.operation === 'batch' || query.operation === 'approval' || query.operation === 'decision' || query.operation === 'impact' || query.operation === 'acceptance' || query.operation === 'resource' ? query.operation : 'snapshot';
  const target = typeof query.target === 'string' ? query.target.slice(0, 80) : '';
  const step = typeof query.step === 'string' && query.step.length <= 36 ? query.step : '';
  const bounded = (name: string, max = 36) => typeof query[name] === 'string' && (query[name] as string).length <= max ? query[name] as string : '';
  const initialContext: Partial<Fields> = { release: bounded('release'), snapshot: bounded('snapshot'), criterion: bounded('criterion'),
    entityType: resourceTypes.includes(bounded('entity_type', 30)) ? bounded('entity_type', 30) : '' };
  return <>
    <div className="top"><div><div className="eyebrow">CONTROLLED COMMANDS</div><h1>Prepare a lifecycle request</h1>
      <p className="muted">Validate, review and copy a lifecycle command request (eight supported forms) for your controlled API client.</p></div></div>
    <CommandWorkbench key={`${operation}:${target}:${step}:${JSON.stringify(initialContext)}`} initialOperation={operation} initialTarget={target} initialStep={step} initialContext={initialContext} />
  </>;
}
