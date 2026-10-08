import { handleGrantStatus } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
async function handle(request: Request) { return handleGrantStatus(request, process.env); }
export { handle as GET, handle as POST };
