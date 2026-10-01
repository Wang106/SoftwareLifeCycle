
import { Localized, LocalizedAttributes } from "../../components/localized";
import ProductionCatalog from '../../components/production-catalog';
export default async function Page({ searchParams }: { searchParams: Promise<Record<string,string | undefined>> }) {
  return <ProductionCatalog kind='deployments' filters={await searchParams} />;
}
