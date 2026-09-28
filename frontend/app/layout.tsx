import './globals.css';
import Link from 'next/link';
export default function RootLayout({children}:{children:React.ReactNode}){return <html><body><div className="shell"><aside className="side"><div className="brand">SoftwareLifeCycle</div><nav className="nav"><Link href="/">Dashboard</Link><Link href="/releases/application">Releases</Link><a>Suppliers</a><a>Customers</a><a>Changes</a><a>Testing</a><a>Distribution</a><a>Deployments</a><a>Issues</a><a>Approvals</a></nav></aside><main className="main">{children}</main></div></body></html>}
