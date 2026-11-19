import {handlePrivateUpload} from '../../../lib/private-upload-proxy';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export function PUT(request:Request) { return handlePrivateUpload(request,process.env,'content'); }
