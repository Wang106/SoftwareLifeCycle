import {Suspense} from 'react';
import ApplicationComponentDeclaration from '../../../../../../components/application-component-declaration';
import {authConfig,applicationComponentDeclarationConfigured} from '../../../../../../lib/browser-auth';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{releaseId:string}>}){
 const {releaseId}=await params;
 let enabled=false,uploadEnabled=false;
 try{const config=await authConfig(process.env);enabled=applicationComponentDeclarationConfigured(process.env,config);uploadEnabled=process.env.PRIVATE_UPLOAD_MODE==='enabled'&&!!config&&process.env.PRIVATE_UPLOAD_APPROVED_API_BASE_URL===config.session.apiBase&&process.env.PRIVATE_UPLOAD_APPROVED_APP_ORIGIN===config.session.origin;}catch{/* Preparation stays editable without enabling writes. */}
 return <Suspense fallback={null}><ApplicationComponentDeclaration enabled={enabled} uploadEnabled={uploadEnabled} releaseId={releaseId}/></Suspense>;
}
