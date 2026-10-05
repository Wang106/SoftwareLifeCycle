import ChangeIssueCatalog, { type CatalogSearch } from "../../components/change-issue-catalog";

export default async function Page({searchParams}: {searchParams: Promise<CatalogSearch>}) {
  return ChangeIssueCatalog({kind: "issues", search: await searchParams});
}
