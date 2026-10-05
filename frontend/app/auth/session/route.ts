import { handleAuth } from '../../../lib/browser-auth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

async function handle(request: Request) {
  return handleAuth(request, 'session', process.env);
}
export { handle as GET, handle as POST };
