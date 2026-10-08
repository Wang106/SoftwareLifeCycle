import { handleAdminRegistration } from '../../../lib/browser-auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export function GET(request: Request) { return handleAdminRegistration(request, process.env); }
export function POST(request: Request) { return handleAdminRegistration(request, process.env); }
