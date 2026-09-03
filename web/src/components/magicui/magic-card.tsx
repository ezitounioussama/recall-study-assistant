"use client";

/**
 * MagicUI MagicCard, reduced to the light theme: a soft spotlight in Action
 * Blue follows the pointer across the card. The MagicUI original carries a
 * dark-mode branch and a theme hook; this site has one theme.
 */
import { useCallback, type ReactNode } from "react";
import { motion, useMotionTemplate, useMotionValue } from "motion/react";
import { cn } from "@/lib/utils";

export function MagicCard({
  children,
  className,
  gradientSize = 220,
}: {
  children?: ReactNode;
  className?: string;
  gradientSize?: number;
}) {
  const mouseX = useMotionValue(-gradientSize);
  const mouseY = useMotionValue(-gradientSize);

  const onMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      mouseX.set(e.clientX - rect.left);
      mouseY.set(e.clientY - rect.top);
    },
    [mouseX, mouseY],
  );
  const reset = useCallback(() => {
    mouseX.set(-gradientSize);
    mouseY.set(-gradientSize);
  }, [mouseX, mouseY, gradientSize]);

  return (
    <div className={cn("group relative isolate overflow-hidden rounded-lg border border-hairline bg-canvas", className)} onPointerMove={onMove} onPointerLeave={reset}>
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: useMotionTemplate`radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px, color-mix(in srgb, var(--color-primary) 12%, transparent), transparent 100%)`,
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
