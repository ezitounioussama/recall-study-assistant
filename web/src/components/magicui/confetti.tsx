"use client";

/**
 * MagicUI Confetti, reduced to what the review screen needs: a canvas you can
 * fire from a ref. Colours are read from the design tokens at fire time, so
 * the burst is in the system's palette and no hex lives in this file.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, type ComponentPropsWithoutRef } from "react";
import confetti, { type CreateTypes, type Options } from "canvas-confetti";

export type ConfettiRef = { fire: (options?: Options) => void };

const TOKEN_COLOURS = ["--color-primary", "--color-primary-on-dark", "--color-ink", "--color-surface-chip-translucent"];

function tokenColours(): string[] {
  const styles = getComputedStyle(document.documentElement);
  return TOKEN_COLOURS.map((t) => styles.getPropertyValue(t).trim()).filter(Boolean);
}

export const Confetti = forwardRef<ConfettiRef, ComponentPropsWithoutRef<"canvas">>(function Confetti(props, ref) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const instance = useRef<CreateTypes | null>(null);

  useEffect(() => {
    if (canvasRef.current && !instance.current) {
      instance.current = confetti.create(canvasRef.current, { resize: true, useWorker: true });
    }
    return () => {
      instance.current?.reset();
      instance.current = null;
    };
  }, []);

  const fire = useCallback((options: Options = {}) => {
    void instance.current?.({
      particleCount: 90,
      spread: 70,
      startVelocity: 35,
      gravity: 0.9,
      ticks: 220,
      scalar: 0.9,
      colors: tokenColours(),
      origin: { y: 0.6 },
      ...options,
    });
  }, []);

  useImperativeHandle(ref, () => ({ fire }), [fire]);

  return <canvas ref={canvasRef} {...props} />;
});
