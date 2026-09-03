/**
 * A bento grid in the system's grammar. MagicUI's version depends on shadcn's
 * Button and Radix icons and ships its own neutral greys; this one is written
 * against the design tokens directly — hairline border, 18px radius, canvas
 * surface, parchment on hover — and takes a live `background` node so each
 * card can carry a small working demo.
 */
import Link from "next/link";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function BentoGrid({ children, className, ...props }: ComponentPropsWithoutRef<"div">) {
  return (
    <div className={cn("grid w-full auto-rows-[22rem] grid-cols-1 gap-lg md:grid-cols-3", className)} {...props}>
      {children}
    </div>
  );
}

export function BentoCard({
  name,
  className,
  background,
  description,
  href,
  cta,
}: {
  name: string;
  className?: string;
  background: ReactNode;
  description: string;
  href: string;
  cta: string;
}) {
  return (
    <div
      className={cn(
        "group relative flex flex-col justify-end overflow-hidden rounded-lg border border-hairline bg-canvas transition-colors duration-300 hover:bg-surface-pearl",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0">{background}</div>

      <div className="relative z-10 flex flex-col gap-xs bg-linear-to-t from-canvas via-canvas/90 to-transparent p-lg pt-xxl transition-transform duration-300 lg:group-hover:-translate-y-8">
        <h3 className="text-tagline text-ink">{name}</h3>
        <p className="max-w-[40ch] text-body text-lead-grey">{description}</p>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex translate-y-8 items-center p-lg opacity-0 transition-all duration-300 lg:group-hover:translate-y-0 lg:group-hover:opacity-100">
        <Link href={href} className="pointer-events-auto text-body-strong text-primary" data-pressable>
          {cta} <span aria-hidden>›</span>
        </Link>
      </div>
    </div>
  );
}
