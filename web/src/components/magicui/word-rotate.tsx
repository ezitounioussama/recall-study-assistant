"use client";

/** MagicUI WordRotate, vendored as an inline span so it can sit inside a sentence. */
import { useEffect, useState } from "react";
import { AnimatePresence, motion, type MotionProps } from "motion/react";
import { cn } from "@/lib/utils";

interface WordRotateProps {
  words: string[];
  duration?: number;
  motionProps?: MotionProps;
  className?: string;
}

export function WordRotate({
  words,
  duration = 2600,
  motionProps = {
    initial: { opacity: 0, y: 24, filter: "blur(4px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    exit: { opacity: 0, y: -24, filter: "blur(4px)" },
    transition: { duration: 0.35, ease: "easeOut" },
  },
  className,
}: WordRotateProps) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setIndex((i) => (i + 1) % words.length), duration);
    return () => clearInterval(interval);
  }, [words, duration]);

  return (
    <span className="inline-grid overflow-hidden align-baseline [&>*]:col-start-1 [&>*]:row-start-1">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span key={words[index]} className={cn("inline-block", className)} {...motionProps}>
          {words[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
