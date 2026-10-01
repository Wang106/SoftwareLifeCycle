
import { Localized, LocalizedAttributes } from "../../../components/localized";
import DistributionCatalog from '../../../components/distribution-catalog';
export default async function Page({ searchParams }: { searchParams: Promise<Record<string,string | undefined>> }) {
  return <DistributionCatalog kind='deliveries' filters={await searchParams} />;
}
