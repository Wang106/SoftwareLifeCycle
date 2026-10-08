import { handleGovernanceCommand } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleGovernanceCommand(request, process.env, 'submit'); }
export function POST(request: Request) { return handleGovernanceCommand(request, process.env, 'submit'); }
