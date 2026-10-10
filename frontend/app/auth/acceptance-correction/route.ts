import { handleAcceptanceCorrection } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleAcceptanceCorrection(request, process.env, 'submit'); }
export function POST(request: Request) { return handleAcceptanceCorrection(request, process.env, 'submit'); }

