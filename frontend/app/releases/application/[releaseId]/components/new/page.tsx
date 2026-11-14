import {Suspense} from 'react';
import ApplicationComponentDeclaration from '../../../../../../components/application-component-declaration';
import {authConfig,applicationComponentDeclarationConfigured} from '../../../../../../lib/browser-auth';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{releaseId:string}>}){
 const {releaseId}=await params;
 let enabled=false;
 try{enabled=applicationComponentDeclarationConfigured(process.env,await authConfig(process.env));}catch{/* Preparation stays editable without enabling writes. */}
 return <Suspense fallback={null}><ApplicationComponentDeclaration enabled={enabled} releaseId={releaseId}/></Suspense>;
}
