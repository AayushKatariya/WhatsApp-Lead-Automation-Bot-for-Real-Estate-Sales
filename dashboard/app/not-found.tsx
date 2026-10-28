import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16 text-center">
      <div>
        <p className="text-lg font-semibold">Not found</p>
        <p className="mt-1 text-sm text-muted">This page doesn&apos;t exist, or it isn&apos;t one of your leads.</p>
        <Link href="/" className="mt-5 inline-block text-sm font-medium text-accent hover:underline">
          Back to leads
        </Link>
      </div>
    </main>
  );
}
