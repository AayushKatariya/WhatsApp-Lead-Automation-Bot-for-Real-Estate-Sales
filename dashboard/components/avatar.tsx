export function Avatar({ name, phone, size = "md" }: { name: string; phone: string; size?: "md" | "lg" }) {
  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || phone.slice(-2);
  const dims = size === "lg" ? "h-12 w-12 text-base" : "h-10 w-10 text-sm";
  return (
    <span
      className={`flex ${dims} shrink-0 items-center justify-center rounded-full bg-accent-soft font-semibold text-accent`}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}
