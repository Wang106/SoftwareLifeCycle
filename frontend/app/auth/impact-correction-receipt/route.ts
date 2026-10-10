import {handleImpactCorrection} from '../../../lib/browser-auth';
export const dynamic='force-dynamic';
export const runtime='nodejs';
export function GET(request:Request){return handleImpactCorrection(request,process.env,'recover');}
export function POST(request:Request){return handleImpactCorrection(request,process.env,'recover');}

