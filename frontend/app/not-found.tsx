import Link from 'next/link';
import { Localized } from '../components/localized';
export default function NotFound() {
  return <div className="card"><h1><Localized>{'Page not found'}</Localized></h1>
    <p><Localized>{'The requested page is unavailable.'}</Localized></p>
    <Link href="/"><Localized>{'Back to dashboard'}</Localized></Link></div>;
}
