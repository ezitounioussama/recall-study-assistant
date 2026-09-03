"use client";

/**
 * MagicUI TextAnimate, vendored and trimmed to the three presets the site
 * uses. Splits a string into words (or characters) and staggers them in.
 */
import { memo } from "react";
import { AnimatePresence, motion, type Variants } from "motion/react";
import { cn } from "@/lib/utils";

type Preset = "fadeIn" | "blurIn" | "blurInUp";
type Split = "word" | "character" | "text";

const ITEM: Record<Preset, Variants> = {
  fadeIn: {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { duration: 0.35 } },
    exit: { opacity: 0, y: 16, transition: { duration: 0.3 } },
  },
  blurIn: {
    hidden: { opacity: 0, filter: "blur(10px)" },
    show: { opacity: 1, filter: "blur(0px)", transition: { duration: 0.35 } },
    exit: { opacity: 0, filter: "blur(10px)", transition: { duration: 0.3 } },
  },
  blurInUp: {
    hidden: { opacity: 0, filter: "blur(10px)", y: 16 },
    show: { opacity: 1, filter: "blur(0px)", y: 0, transition: { y: { duration: 0.35 }, opacity: { duration: 0.45 }, filter: { duration: 0.35 } } },
    exit: { opacity: 0, filter: "blur(10px)", y: 16, transition: { duration: 0.3 } },
  },
};

const ELEMENTS = { p: motion.p, h1: motion.h1, h2: motion.h2, h3: motion.h3, span: motion.span, div: motion.div } as const;

interface TextAnimateProps {
  children: string;
  className?: string;
  segmentClassName?: string;
  delay?: number;
  duration?: number;
  as?: keyof typeof ELEMENTS;
  by?: Split;
  startOnView?: boolean;
  once?: boolean;
  animation?: Preset;
}

function TextAnimateBase({
  children,
  delay = 0,
  duration = 0.4,
  className,
  segmentClassName,
  as = "p",
  startOnView = true,
  once = true,
  by = "word",
  animation = "blurInUp",
}: TextAnimateProps) {
  const Component = ELEMENTS[as];
  const segments = by === "word" ? children.split(/(\s+)/) : by === "character" ? children.split("") : [children];
  const container: Variants = {
    hidden: { opacity: 1 },
    show: { opacity: 1, transition: { delayChildren: delay, staggerChildren: duration / segments.length } },
    exit: { opacity: 0, transition: { staggerChildren: duration / segments.length, staggerDirection: -1 } },
  };

  return (
    <AnimatePresence mode="popLayout">
      <Component
        variants={container}
        initial="hidden"
        whileInView={startOnView ? "show" : undefined}
        animate={startOnView ? undefined : "show"}
        exit="exit"
        className={cn("whitespace-pre-wrap", className)}
        viewport={{ once }}
        aria-label={children}
      >
        {segments.map((segment, i) => (
          <motion.span
            key={`${by}-${segment}-${i}`}
            variants={ITEM[animation]}
            className={cn("inline-block whitespace-pre", segmentClassName)}
            aria-hidden
          >
            {segment}
          </motion.span>
        ))}
      </Component>
    </AnimatePresence>
  );
}

export const TextAnimate = memo(TextAnimateBase);
