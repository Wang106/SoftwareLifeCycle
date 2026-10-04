import ManufacturingProfile from '../../../../components/manufacturing-profile';
import type { ManufacturingSearch } from '../../../../lib/manufacturing-views';
export default async function Page({params,searchParams}: {params: Promise<{id: string}>; searchParams: Promise<ManufacturingSearch>}) {
  const {id} = await params;
  return <ManufacturingProfile identifier={id} search={await searchParams}/>;
}
