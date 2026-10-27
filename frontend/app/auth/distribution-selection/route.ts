import { handlePrivateDistributionSelection } from '../../../lib/browser-auth';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function GET(request: Request) { return handlePrivateDistributionSelection(request, process.env); }
export function POST(request: Request) { return handlePrivateDistributionSelection(request, process.env); }
