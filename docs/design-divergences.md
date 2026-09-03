# Where the live page differs from the analysis

`docs/design-language.md` is an analysis of Apple's homepage, environment page,
store, iPhone 17 Pro buy page and accessories index. The UI in this repository
is built against a different surface — **apple.com/ma/iphone-air** — and that
page contradicts the analysis in four places.

Each divergence follows the live page, because a design document describes a
system and the shipped page *is* the system. All four are listed here so nobody
reads the code as sloppiness against the spec.

## 1. Chrome carries a shadow

**The document says:** "Apple uses **exactly one** drop-shadow, and it is
applied to photographic product imagery — never to cards, never to buttons,
never to text." Elevation in the UI comes from surface-colour change and
backdrop blur.

**The live page does:** floats the product nav as a **rounded white island**,
inset from both edges, with a soft shadow beneath it. It is chrome, and it is
elevated.

**Resolution:** a second token, `--shadow-float`, used only by the floating nav.
The product shadow keeps its exclusive claim on imagery.

## 2. Display headings are weight 400, not 600

**The document says:** "Weight 600, not 700, for headlines… Mid-weight readings
always use 600."

**The live page does:** sets the "Points forts" section heading at **40px /
weight 400** — measured from the live DOM, not inferred.

**Resolution:** `--text-section-head` is 40px/400. The document's
`--text-display-lg` (40px/600) still exists and is still correct for the
homepage; the product page is quieter. Weight 400 at 40px is what makes the
reference page read as calm rather than as marketing.

## 3. Body copy is two-tone

**The document says:** one near-black tone for all text on light surfaces —
`ink` and `body` are the same hex.

**The live page does:** sets long-form lead copy in a **grey** (`#6e6e73`) with
individual phrases in full ink, so a paragraph reads two-tone and the eye lands
on the claims without a heading.

**Resolution:** `--color-lead-grey`, added to the specification's front matter
rather than to an allowlist in the token checker — the checker's premise is that
the spec is authoritative, so silencing it would invert the tool.

Emphasis is applied as **colour, not weight**. A `<strong>` here would imply a
mid-weight the document explicitly excludes from the ladder.

## 4. The top bar is white, not black

**The document says:** "Keep the global nav `surface-black` (true black) — it's
the only place pure black appears on most pages."

**The live page does:** a white bar with ink text and a blur.

**Resolution:** both exist. `GlobalNav` (black) is the homepage's; the product
surface uses `ProductTopBar` (white). A black bar above a white product hero
reads as a lid — the document's own claim that the nav should recede argues for
the white one here.

## What did not change

The single accent (`#0066cc` and its two siblings), the pill-means-action rule,
the 17px body size, the radius grammars, the 44px touch target, the
`scale(0.95)` press state, and the absence of hover styling. The parts of the
document that describe the *system* rather than one surface all held up.
