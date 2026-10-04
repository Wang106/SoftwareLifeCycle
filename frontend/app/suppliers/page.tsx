import OrganizationCatalog from '../../components/organization-catalog';
import type { OrganizationSearch } from '../../lib/organization-views';
export default async function Page({ searchParams }: { searchParams: Promise<OrganizationSearch> }) {
  return <OrganizationCatalog kind="suppliers" search={await searchParams}/>;
}
