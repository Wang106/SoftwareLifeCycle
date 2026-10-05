import ReleaseCatalog, { type ReleaseSearch } from "../../../components/release-catalog";

export default async function Page({searchParams}: {searchParams: Promise<ReleaseSearch>}) {
  return ReleaseCatalog({kind: "application", search: await searchParams});
}
