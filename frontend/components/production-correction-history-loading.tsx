import { Localized } from './localized';

export default function ProductionCorrectionHistoryLoading() {
  return <Localized><section className="panel" role="status" aria-live="polite" aria-busy="true">
    <h1><Localized>{'Loading correction history'}</Localized></h1>
    <p><Localized>{'Waiting for read-only history. No recorded facts have been confirmed yet.'}</Localized></p>
  </section></Localized>;
}
