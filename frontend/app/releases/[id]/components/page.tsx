
import { Localized, LocalizedAttributes } from "../../../../components/localized";
import { redirect } from 'next/navigation';
import { legacyReleaseTarget } from '../../../../lib/legacy-release';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  redirect(await legacyReleaseTarget((await params).id, '/components'));
}
