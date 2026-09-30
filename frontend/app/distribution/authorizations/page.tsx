import DistributionCatalog from '../../../components/distribution-catalog';
export default async function Page({ searchParams }: { searchParams: Promise<Record<string,string | undefined>> }) {
  return <DistributionCatalog kind='authorizations' filters={await searchParams} />;
}
