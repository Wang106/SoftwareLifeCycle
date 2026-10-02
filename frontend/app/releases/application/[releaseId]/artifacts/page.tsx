import { AsrPolicy } from '../../../../../components/asr-policy';

export default async function Page({ params, searchParams }: {
  params: Promise<{ releaseId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { releaseId } = await params;
  return <AsrPolicy releaseId={releaseId} search={await searchParams} />;
}
