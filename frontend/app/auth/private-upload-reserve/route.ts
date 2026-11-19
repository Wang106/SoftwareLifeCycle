import {handlePrivateUpload} from '../../../lib/private-upload-proxy';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function POST(request:Request) { return handlePrivateUpload(request,process.env,'reserve'); }
