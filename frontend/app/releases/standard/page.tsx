import SupplierReleaseCatalog from '../../../components/supplier-release-catalog';
import type { ReleaseSearch } from '../../../components/release-catalog';
export default async function Page({searchParams}: {searchParams: Promise<ReleaseSearch>}) {
  return SupplierReleaseCatalog({search: await searchParams});
}
