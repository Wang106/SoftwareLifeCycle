'use client';
import { Localized } from '../components/localized';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <div className="card"><h1><Localized>{'Page unavailable'}</Localized></h1>
    <p><Localized>{'Please try loading this page again.'}</Localized></p>
    <button type="button" onClick={reset}><Localized>{'Retry loading'}</Localized></button></div>;
}
