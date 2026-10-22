import {Localized} from '../../components/localized';

export default function Loading() {
  return <Localized>
    <div className="top"><div><h1><Localized>{'Loading demonstration data'}</Localized></h1>
      <p className="muted"><Localized>{'Waiting for the read-only demonstration API. This may take a moment on a cold start.'}</Localized></p></div></div>
    <section className="panel" aria-busy="true">
      <h2><Localized>{'Preparing the read-only overview'}</Localized></h2>
      <div className="demo-loading">
        <span className="demo-loading-bar"/>
        <span className="demo-loading-bar"/>
        <span className="demo-loading-bar"/>
      </div>
      <p className="muted"><Localized>{'No sample evidence is fabricated while waiting.'}</Localized></p>
    </section>
  </Localized>;
}
