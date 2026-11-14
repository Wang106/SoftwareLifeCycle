import { handleApplicationComponentDeclaration } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handleApplicationComponentDeclaration(request, process.env, 'context'); }
export function POST(request: Request) { return handleApplicationComponentDeclaration(request, process.env, 'context'); }
