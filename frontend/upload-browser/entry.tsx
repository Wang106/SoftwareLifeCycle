// Test-only entry; not included in app routes or production bundles.
import {createRoot} from 'react-dom/client';
import PrivateUploadPicker from '../components/private-upload-picker';
import {LanguageProvider} from '../components/localized';
const p=window.location.pathname;
if(!['/upload','/disabled'].includes(p)||window.location.search||window.location.hash)throw Error('invalid fixture page');
createRoot(document.getElementById('fixture-root')!).render(<LanguageProvider initialLocale="en"><p>Synthetic browser and relay fixture. Not real identity or production storage.</p><PrivateUploadPicker componentId="52345678-1234-4234-8234-123456789abc" enabled={p==='/upload'}/></LanguageProvider>);
