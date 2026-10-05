import OrganizationProfile from '../../../components/organization-profile';
import type { OrganizationSearch } from '../../../lib/organization-views';
export default async function Page({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<OrganizationSearch> }) {
  const { id } = await params;
  return <OrganizationProfile kind="suppliers" identifier={id} search={await searchParams}/>;
}
