"use client";

/** MagicUI TypingAnimation, vendored: text typed one grapheme at a time, with an optional blinking cursor. */
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { motion, useInView, type MotionProps } from "motion/react";
import { cn } from "@/lib/utils";

interface TypingAnimationProps extends Omit<MotionProps, "children"> {
  children?: string;
  words?: string[];
  className?: string;
  duration?: number;
  deleteSpeed?: number;
  delay?: number;
  pauseDelay?: number;
  loop?: boolean;
  startOnView?: boolean;
  showCursor?: boolean;
}

export function TypingAnimation({
  children,
  words,
  className,
  duration = 60,
  deleteSpeed,
  delay = 0,
  pauseDelay = 1400,
  loop = false,
  startOnView = true,
  showCursor = true,
  ...props
}: TypingAnimationProps) {
  const [displayed, setDisplayed] = useState("");
  const [wordIndex, setWordIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const [phase, setPhase] = useState<"typing" | "pause" | "deleting">("typing");
  const ref = useRef<HTMLSpanElement | null>(null);
  const isInView = useInView(ref as RefObject<Element>, { amount: 0.3, once: true });

  const list = useMemo(() => words ?? (children ? [children] : []), [words, children]);
  const multiple = list.length > 1;
  const deletingSpeed = deleteSpeed ?? duration / 2;
  const shouldStart = startOnView ? isInView : true;

  useEffect(() => {
    if (!shouldStart || list.length === 0) return;
    const wait =
      delay > 0 && displayed === "" ? delay : phase === "typing" ? duration : phase === "deleting" ? deletingSpeed : pauseDelay;

    const timeout = setTimeout(() => {
      const graphemes = Array.from(list[wordIndex] ?? "");
      if (phase === "typing") {
        if (charIndex < graphemes.length) {
          setDisplayed(graphemes.slice(0, charIndex + 1).join(""));
          setCharIndex(charIndex + 1);
        } else if ((multiple || loop) && (wordIndex < list.length - 1 || loop)) {
          setPhase("pause");
        }
      } else if (phase === "pause") {
        setPhase("deleting");
      } else if (charIndex > 0) {
        setDisplayed(graphemes.slice(0, charIndex - 1).join(""));
        setCharIndex(charIndex - 1);
      } else {
        setWordIndex((wordIndex + 1) % list.length);
        setPhase("typing");
      }
    }, wait);
    return () => clearTimeout(timeout);
  }, [shouldStart, phase, charIndex, wordIndex, displayed, list, multiple, loop, duration, deletingSpeed, pauseDelay, delay]);

  const graphemes = Array.from(list[wordIndex] ?? "");
  const complete = !loop && wordIndex === list.length - 1 && charIndex >= graphemes.length && phase !== "deleting";
  const cursor = showCursor && !complete;

  return (
    <motion.span ref={ref} className={cn("inline-block", className)} {...props}>
      {displayed}
      {cursor ? <span className="inline-block animate-blink-cursor">|</span> : null}
    </motion.span>
  );
}
