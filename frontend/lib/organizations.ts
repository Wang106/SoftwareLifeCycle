export type Software = { code: string; name: string; type: string | null; status: string; standard_version: string | null };
export type Supplier = { code: string; name: string; country: string | null; website: string | null; description: string | null; status: string; software: Software[] };
export type ReleaseRef = { id: string; version: string; status: string } | null;
export type ProjectRef = { id: string; code: string; name: string; status: string; release: ReleaseRef };
export type Customer = { code: string; name: string; region: string | null; status: string; projects: ProjectRef[] };
export type Project = { id: string; code: string; name: string; status: string; vehicle_platform: string | null; customer: { code: string; name: string }; release: ReleaseRef; sites: { code: string; name: string; status: string }[] };
