/**
 * A placeholder for routes the navigation links to but that later pull requests
 * build. It exists so the nav is coherent while the app is being built in
 * sequence — a link to a 404 reads as a bug, and reviewers cannot tell an
 * unfinished route from a broken one.
 *
 * Styled in the design language rather than left as default Next output,
 * because a bare 404 breaks the surface rhythm on the way through.
 */
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SubNav } from "@/components/ui/nav";
import { Tile, TileHeader } from "@/components/ui/tile";

export function NotBuiltYet({
  category,
  headline,
  what,
  pr,
}: {
  category: string;
  headline: string;
  what: string;
  pr: string;
}) {
  return (
    <>
      <SubNav category={category}>
        <Link href="/" data-pressable>
          <Button variant="dark-utility">Back to overview</Button>
        </Link>
      </SubNav>

      <Tile surface="parchment">
        <TileHeader eyebrow={`Coming in ${pr}`} headline={headline} tagline={what}>
          <Link href="/#how" data-pressable>
            <Button variant="secondary">How it will work</Button>
          </Link>
        </TileHeader>
      </Tile>
    </>
  );
}
