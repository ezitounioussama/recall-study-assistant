"use client";

/** MagicUI ScrollProgress, vendored: a hairline at the top of the page that fills as you read. */
import { motion, useScroll } from "motion/react";
import { cn } from "@/lib/utils";

export function ScrollProgress({ className }: { className?: string }) {
  const { scrollYProgress } = useScroll();
  return (
    <motion.div
      className={cn("fixed inset-x-0 top-0 z-[60] h-0.5 origin-left bg-primary", className)}
      style={{ scaleX: scrollYProgress }}
    />
  );
}
