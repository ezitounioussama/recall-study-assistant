/** A field of hairline dots behind a hero, fading out towards the edges. */
import { useId } from "react";
import { cn } from "@/lib/utils";

export function DotPattern({
  width = 20,
  height = 20,
  radius = 1,
  className,
}: {
  width?: number;
  height?: number;
  radius?: number;
  className?: string;
}) {
  const id = useId();
  return (
    <svg
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0 size-full fill-hairline mask-[radial-gradient(ellipse_at_center,black_30%,transparent_75%)]",
        className,
      )}
    >
      <defs>
        <pattern id={id} width={width} height={height} patternUnits="userSpaceOnUse">
          <circle cx={width / 2} cy={height / 2} r={radius} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}
