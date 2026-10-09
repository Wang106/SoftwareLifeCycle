import { handleEvidenceCommand } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleEvidenceCommand(request, process.env, 'submit'); }
export function POST(request: Request) { return handleEvidenceCommand(request, process.env, 'submit'); }
