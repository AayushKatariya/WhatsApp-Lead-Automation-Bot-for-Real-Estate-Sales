/** The part of node-postgres' API the queries use. Tests pass PGlite, which has the same shape. */
export type Db = {
  query<T>(text: string, params?: unknown[]): Promise<{ rows: T[] }>;
};

export type Role = "owner" | "sales";

/** Someone signed in to the dashboard. Owners see every lead; sales reps only leads of their projects. */
export type User = {
  email: string;
  name: string;
  role: Role;
  siteIds: string[];
};

export type Project = { site_id: string; site_name: string };
