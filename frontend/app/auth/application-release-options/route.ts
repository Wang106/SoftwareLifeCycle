import { handleApplicationReleaseCreation } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleApplicationReleaseCreation(request, process.env, 'options'); }
export function POST(request: Request) { return handleApplicationReleaseCreation(request, process.env, 'options'); }
