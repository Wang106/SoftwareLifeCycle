import { handlePrivateEvidenceSelection } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handlePrivateEvidenceSelection(request, process.env); }
export function POST(request: Request) { return handlePrivateEvidenceSelection(request, process.env); }
