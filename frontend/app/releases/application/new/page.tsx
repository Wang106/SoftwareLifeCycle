import {Suspense} from 'react';
import ApplicationReleaseCreation from '../../../../components/application-release-creation';
import {authConfig,applicationReleaseCreationConfigured} from '../../../../lib/browser-auth';
export const dynamic='force-dynamic';
export default async function Page(){
 let enabled=false;
 try{enabled=applicationReleaseCreationConfigured(process.env,await authConfig(process.env));}catch{/* Public preparation remains available without identity or writes. */}
 return <Suspense fallback={null}><ApplicationReleaseCreation enabled={enabled}/></Suspense>;
}
