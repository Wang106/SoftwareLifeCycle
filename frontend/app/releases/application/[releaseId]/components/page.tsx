
import { Localized } from "../../../../../components/localized";
import { AsrComponentPages } from '../../../../../components/asr-component-pages';
import Link from 'next/link';
import { apiGet } from '../../../../../lib/api';

type Components = {
  release_id: string; version: string; base_release: { id: string; version: string } | null;
  component_count: number; unlinked_base_count: number;
};

export default async function Page({ params, searchParams }: { params: Promise<{ releaseId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { releaseId } = await params;
  const base = `/releases/application/${encodeURIComponent(releaseId)}`;
  const data = await apiGet<Components>(`/api/v1/releases/application/id/${encodeURIComponent(releaseId)}/components/summary`);
  if (!data || data.release_id !== releaseId) return <section className="panel"><h1><Localized>{"Components unavailable"}</Localized></h1>
    <p className="muted"><Localized>{"The application release was not found or the API could not be reached."}</Localized></p>
    <Link href={base}><Localized>{"← Release profile"}</Localized></Link></section>;
  return <>
    <div className="top"><div><div className="eyebrow"><Localized>{"APPLICATION RELEASE COMPONENTS"}</Localized></div><h1><Localized>{"ASR "}</Localized><Localized>{data.version}</Localized></h1>
      <p className="muted"><Localized>{"Declared component differences against "}</Localized><Localized>{data.base_release ? `SSR ${data.base_release.version}` : 'an unrecorded SSR base'}</Localized><Localized>{"."}</Localized></p></div></div>
    <AsrComponentPages releaseId={releaseId} baseReleaseId={data.base_release?.id ?? null}
      search={await searchParams} componentCount={data.component_count} unlinkedCount={data.unlinked_base_count} />
    <p className="datasource"><Link href={base}><Localized>{"← Release profile"}</Localized></Link></p>
  </>;
}
