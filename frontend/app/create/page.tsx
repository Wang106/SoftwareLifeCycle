import Link from 'next/link';
import { Localized } from '../../components/localized';

const forms = [
  { title: 'Prepare controlled request', description: 'Choose from fourteen existing lifecycle request forms.', href: '/commands' },
  { title: 'Test Release', description: 'Prepare a test release draft from an exact frozen snapshot.', href: '/commands?operation=test-release' },
  { title: 'Delivery Packages', description: 'Prepare a recipient-specific delivery package revision.', href: '/commands?operation=delivery' },
  { title: 'Production Authorizations', description: 'Prepare a production authorization for an exact distribution.', href: '/commands?operation=authorization' },
];
const planned = [
  { title: 'Software Change Request', href: '/changes' },
  { title: 'Issue', href: '/issues' },
  { title: 'DVP Plan', href: '/testing/dvp' },
  { title: 'Application Release', href: '/releases/application' },
];

export default function Page() {
  return <>
    <div className="top"><div>
      <div className="eyebrow"><Localized>{'CREATE'}</Localized></div>
      <h1><Localized>{'Create lifecycle record'}</Localized></h1>
      <p className="muted"><Localized>{'Available forms prepare requests. Submission still requires an approved signed-in environment; the public demo remains read-only.'}</Localized></p>
      <p className="muted"><Localized>{'File upload is not implemented. Resource references do not upload or store files.'}</Localized></p>
    </div></div>
    <div className="creategrid"><Localized>{forms.map(item =>
      <Link className="createcard" href={item.href} prefetch={false} key={item.title}>
        <b><Localized>{item.title}</Localized></b>
        <span><Localized>{item.description}</Localized></span>
        <strong className="createaction"><Localized>{'Open form'}</Localized></strong>
      </Link>
    )}</Localized><Localized>{planned.map(item =>
      <article className="createcard createcard-unavailable" key={item.title}>
        <b><Localized>{item.title}</Localized></b>
        <span><Localized>{'Creation form not implemented'}</Localized></span>
        <Link className="createbrowse" href={item.href} prefetch={false}><Localized>{'Browse existing records'}</Localized></Link>
      </article>
    )}</Localized></div>
  </>;
}
