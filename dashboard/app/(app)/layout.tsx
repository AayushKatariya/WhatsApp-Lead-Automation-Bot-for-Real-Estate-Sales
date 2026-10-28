import Link from "next/link";
import { Suspense } from "react";
import { signOut } from "@/app/actions";
import { Skeleton } from "@/components/ui";
import { getCurrentUser } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-xs font-bold text-accent-text">
              L
            </span>
            Leads
          </Link>
          <Suspense fallback={<Skeleton className="ml-auto h-6 w-40" />}>
            <UserNav />
          </Suspense>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}

async function UserNav() {
  const user = await getCurrentUser();
  return (
    <>
      {user.role === "owner" && (
        <nav className="text-sm">
          <Link href="/team" className="rounded-md px-2 py-1 text-muted hover:bg-surface-2 hover:text-text">
            Team
          </Link>
        </nav>
      )}
      <div className="ml-auto flex items-center gap-3 text-sm">
        <span className="hidden text-right leading-tight sm:block">
          <span className="block font-medium">{user.name || user.email}</span>
          <span className="block text-xs text-muted">{user.role === "owner" ? "Owner" : "Sales"}</span>
        </span>
        <form action={signOut}>
          <button className="rounded-md px-2 py-1 text-muted hover:bg-surface-2 hover:text-text">Sign out</button>
        </form>
      </div>
    </>
  );
}
