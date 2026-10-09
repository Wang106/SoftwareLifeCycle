import { handleDistributionCommand } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleDistributionCommand(request, process.env, 'recover'); }
export function POST(request: Request) { return handleDistributionCommand(request, process.env, 'recover'); }
