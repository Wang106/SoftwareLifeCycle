// Test-only component entry. This is not a Next route or an authenticated session.
import {createRoot} from 'react-dom/client';
import AuthorizationApprovalWorkbench from '../components/authorization-approval-workbench';
import {LanguageProvider} from '../components/localized';

const pages:Record<string,{contextEnabled?:boolean;submissionEnabled?:boolean;recoveryEnabled?:boolean}>={
  '/component/approval':{contextEnabled:true,submissionEnabled:true,recoveryEnabled:true},
  '/component/readonly':{contextEnabled:true,submissionEnabled:false,recoveryEnabled:true},
  // Deliberately omit capabilities to exercise the component's default-off props.
  '/component/disabled':{},
};
const props=pages[window.location.pathname];
if(!props||window.location.search||window.location.hash)throw Error('Unsupported component fixture page');
const root=document.getElementById('component-root');
if(!root)throw Error('Missing component fixture root');
createRoot(root).render(<LanguageProvider initialLocale="en">
  <p>Isolated synthetic component fixture. Not a login or production route.</p>
  <AuthorizationApprovalWorkbench authorizationNo="AUTH-原始" {...props}/>
</LanguageProvider>);
