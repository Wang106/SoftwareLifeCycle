import { Localized } from './localized';
export function PageLoading() {
  return <section className="panel page-loading" aria-busy="true" role="status">
    <h2><Localized>{'Loading page data'}</Localized></h2>
    <p className="muted"><Localized>{'The page is ready to navigate. Data will appear when the server responds.'}</Localized></p>
    <div className="demo-loading-bar" aria-hidden="true"/><div className="demo-loading-bar" aria-hidden="true"/>
  </section>;
}
