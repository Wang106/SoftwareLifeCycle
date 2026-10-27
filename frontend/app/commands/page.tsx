import { cookies } from 'next/headers';
import Link from 'next/link';
import { authConfig, privateDistributionSelectionConfigured, firstSubmissionConfigured, governanceSubmissionConfigured, distributionSubmissionConfigured, productionSubmissionConfigured, evidenceSubmissionConfigured, resourceSubmissionConfigured, acceptanceCorrectionSubmissionConfigured, impactCorrectionSubmissionConfigured, impactWithdrawalSubmissionConfigured, releaseDecisionSupersessionSubmissionConfigured, releaseChainRevocationSubmissionConfigured } from '../../lib/browser-auth';
import { resolveSession, SESSION_COOKIE } from '../../lib/browser-session';

import { Localized, LocalizedAttributes } from "../../components/localized";
import CommandWorkbench from '../../components/command-workbench';
import { Operation, Fields, resourceTypes } from '../../lib/command-draft';

export const dynamic = 'force-dynamic';
export default async function Page({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const operation: Operation = query.operation === 'impact-correction' || query.operation === 'impact-withdrawal' ? 'impact' : query.operation === 'actual' || query.operation === 'batch' || query.operation === 'approval' || query.operation === 'decision' || query.operation === 'impact' || query.operation === 'acceptance' || query.operation === 'resource' || query.operation === 'delivery' || query.operation === 'distribution' || query.operation === 'authorization' || query.operation === 'test-release' || query.operation === 'deployment' || query.operation === 'changeover' ? query.operation : 'snapshot';
  const target = typeof query.target === 'string' ? query.target.slice(0, 80) : '';
  const step = typeof query.step === 'string' && query.step.length <= 36 ? query.step : '';
  const bounded = (name: string, max = 36) => typeof query[name] === 'string' && (query[name] as string).length <= max ? query[name] as string : '';
  const initialContext: Partial<Fields> = { productionLine: bounded('line'), release: bounded('release'), snapshot: bounded('snapshot'), criterion: bounded('criterion'),
    entityType: resourceTypes.includes(bounded('entity_type', 30)) ? bounded('entity_type', 30) : '' };
  let config = null;
  try { config = await authConfig(process.env); } catch { /* Do not expose configuration details. */ }
  const selectionConfigured=['delivery','distribution','authorization'].includes(operation)&&privateDistributionSelectionConfigured(process.env,config);
  const configured = firstSubmissionConfigured(process.env, config);
  const governanceConfigured = governanceSubmissionConfigured(process.env, config);
  const distributionConfigured = distributionSubmissionConfigured(process.env, config);
  const productionConfigured = productionSubmissionConfigured(process.env, config);
  const evidenceConfigured = evidenceSubmissionConfigured(process.env, config);
  const resourceConfigured = resourceSubmissionConfigured(process.env, config);
  const impactCorrectionContextRequested = query.operation === 'impact-correction';
  const impactWithdrawalContextRequested = query.operation === 'impact-withdrawal';
  const decisionSupersessionContextRequested = query.operation === 'decision-supersession';
  const releaseChainRevocationContextRequested = query.operation === 'release-chain-revocation';
  const correctionContextRequested = !impactCorrectionContextRequested && !impactWithdrawalContextRequested && !decisionSupersessionContextRequested && !releaseChainRevocationContextRequested && (query.predecessor !== undefined || query.correction_action !== undefined);
  const correctionConfigured = correctionContextRequested && acceptanceCorrectionSubmissionConfigured(process.env, config);
  const AcceptanceCorrectionWorkbench = correctionContextRequested ? (await import('../../components/acceptance-correction-workbench')).default : null;
  const impactCorrectionConfigured = impactCorrectionContextRequested && impactCorrectionSubmissionConfigured(process.env, config);
  const ImpactCorrectionWorkbench = impactCorrectionContextRequested ? (await import('../../components/impact-correction-workbench')).default : null;
  const impactWithdrawalConfigured = impactWithdrawalContextRequested && impactWithdrawalSubmissionConfigured(process.env, config);
  const ImpactWithdrawalWorkbench = impactWithdrawalContextRequested ? (await import('../../components/impact-withdrawal-workbench')).default : null;
  const decisionSupersessionConfigured = decisionSupersessionContextRequested && releaseDecisionSupersessionSubmissionConfigured(process.env, config);
  const ReleaseDecisionSupersessionWorkbench = decisionSupersessionContextRequested ? (await import('../../components/release-decision-supersession-workbench')).default : null;
  const releaseChainRevocationConfigured = releaseChainRevocationContextRequested && releaseChainRevocationSubmissionConfigured(process.env, config);
  const ReleaseChainRevocationWorkbench = releaseChainRevocationContextRequested ? (await import('../../components/release-chain-revocation-workbench')).default : null;
  const anyConfigured = selectionConfigured || configured || governanceConfigured || distributionConfigured || productionConfigured || evidenceConfigured || resourceConfigured || correctionConfigured || impactCorrectionConfigured || impactWithdrawalConfigured || decisionSupersessionConfigured || releaseChainRevocationConfigured;
  const values = anyConfigured ? (await cookies()).getAll(SESSION_COOKIE) : [];
  const identity = anyConfigured && config && values.length === 1 ? await resolveSession(config.session, values[0].value) : null;
  const recoveryEnabled = configured && identity !== null;
  const submissionEnabled = recoveryEnabled && identity?.read_only_mode === false;
  const governanceRecoveryEnabled = governanceConfigured && identity !== null;
  const governanceSubmissionEnabled = governanceRecoveryEnabled && identity?.read_only_mode === false;
  const distributionRecoveryEnabled = distributionConfigured && identity !== null;
  const distributionSubmissionEnabled = distributionRecoveryEnabled && identity?.read_only_mode === false;
  const productionRecoveryEnabled = productionConfigured && identity !== null;
  const productionSubmissionEnabled = productionRecoveryEnabled && identity?.read_only_mode === false;
  const evidenceRecoveryEnabled = evidenceConfigured && identity !== null;
  const evidenceSubmissionEnabled = evidenceRecoveryEnabled && identity?.read_only_mode === false;
  const resourceRecoveryEnabled = resourceConfigured && identity !== null;
  const resourceSubmissionEnabled = resourceRecoveryEnabled && identity?.read_only_mode === false;
  return <>
    {!releaseChainRevocationContextRequested&&<p><Link prefetch={false} href="/commands?operation=release-chain-revocation"><Localized>{'Prepare a permanent revocation →'}</Localized></Link></p>}
    <div className="top"><div><div className="eyebrow"><Localized>{"CONTROLLED COMMANDS"}</Localized></div><h1><Localized>{"Prepare a lifecycle request"}</Localized></h1>
      <p className="muted"><Localized>{"Prepare fourteen lifecycle commands. Approved signed-in environments can submit Snapshot, actual software, batch, approval action, release decision, delivery package, distribution, production authorization, test release, deployment, changeover, impact assessment, acceptance-to-DVP and resource reference requests and query their original audit receipts."}</Localized></p></div></div>
    {AcceptanceCorrectionWorkbench && <AcceptanceCorrectionWorkbench initialContext={{target,criterion:bounded('criterion'),predecessor:bounded('predecessor'),previousDvp:bounded('previous_dvp'),
      previousAction:bounded('previous_action',10)||'ASSIGN',action:bounded('correction_action',10)||'SUPERSEDE'}}
      submissionEnabled={correctionConfigured && identity !== null && identity.read_only_mode === false}
      recoveryEnabled={correctionConfigured && identity !== null}/> }
    {ImpactCorrectionWorkbench && <ImpactCorrectionWorkbench initialContext={{target,release:bounded('release'),snapshot:bounded('snapshot'),predecessor:bounded('predecessor'),
      previousDecision:bounded('previous_decision',20)}}
      submissionEnabled={impactCorrectionConfigured && identity !== null && identity.read_only_mode === false}
      recoveryEnabled={impactCorrectionConfigured && identity !== null}/> }
    {ImpactWithdrawalWorkbench && <ImpactWithdrawalWorkbench initialContext={{target,release:bounded('release'),snapshot:bounded('snapshot'),predecessor:bounded('predecessor'),previousDecision:bounded('previous_decision',20)}}
      submissionEnabled={impactWithdrawalConfigured && identity !== null && identity.read_only_mode === false}
      recoveryEnabled={impactWithdrawalConfigured && identity !== null}/> }
    {ReleaseDecisionSupersessionWorkbench && <ReleaseDecisionSupersessionWorkbench initialContext={{target,release:bounded('release'),snapshot:bounded('snapshot'),
      predecessor:bounded('predecessor'),previousNo:bounded('previous_decision_no',50),previousDecision:bounded('previous_decision',30),previousReadiness:bounded('previous_readiness',30)}}
      submissionEnabled={decisionSupersessionConfigured && identity !== null && identity.read_only_mode === false}
      recoveryEnabled={decisionSupersessionConfigured && identity !== null}/> }
    {ReleaseChainRevocationWorkbench && <ReleaseChainRevocationWorkbench initialContext={{kind:query.kind==='release'||query.kind==='delivery-package'||query.kind==='distribution'||query.kind==='authorization'?({release:'RELEASE','delivery-package':'DELIVERY_PACKAGE',distribution:'DISTRIBUTION',authorization:'AUTHORIZATION'} as const)[query.kind]:undefined,
      targetId:bounded('target'),releaseId:bounded('release'),snapshotId:bounded('snapshot'),decisionId:bounded('decision'),deliveryId:bounded('delivery'),distributionId:bounded('distribution'),authorizationId:bounded('authorization')}}
      submissionEnabled={releaseChainRevocationConfigured && identity !== null && identity.read_only_mode === false}
      recoveryEnabled={releaseChainRevocationConfigured && identity !== null}/> }
    {!decisionSupersessionContextRequested && !releaseChainRevocationContextRequested && <CommandWorkbench selectionEnabled={selectionConfigured&&identity?.principal.principal_type==='USER'} initialOperation={operation} initialTarget={target} initialStep={step} initialContext={initialContext} submissionEnabled={submissionEnabled} recoveryEnabled={recoveryEnabled} governanceSubmissionEnabled={governanceSubmissionEnabled} governanceRecoveryEnabled={governanceRecoveryEnabled} distributionSubmissionEnabled={distributionSubmissionEnabled} distributionRecoveryEnabled={distributionRecoveryEnabled} productionSubmissionEnabled={productionSubmissionEnabled} productionRecoveryEnabled={productionRecoveryEnabled} evidenceSubmissionEnabled={evidenceSubmissionEnabled} evidenceRecoveryEnabled={evidenceRecoveryEnabled} resourceSubmissionEnabled={resourceSubmissionEnabled} resourceRecoveryEnabled={resourceRecoveryEnabled} />}
  </>;
}


