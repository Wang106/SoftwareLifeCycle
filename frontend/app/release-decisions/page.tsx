
import { Localized, LocalizedAttributes } from "../../components/localized";
import GovernanceCatalog from '../../components/governance-catalog';
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|undefined>>}) {return <GovernanceCatalog kind='decisions' filters={await searchParams}/>;}
