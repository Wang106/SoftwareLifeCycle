import ManufacturingCatalog from '../../../components/manufacturing-catalog';
import type { ManufacturingSearch } from '../../../lib/manufacturing-views';
export default async function Page({searchParams}: {searchParams: Promise<ManufacturingSearch>}) {
  return <ManufacturingCatalog search={await searchParams}/>;
}
