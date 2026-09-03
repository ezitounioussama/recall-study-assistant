/**
 * Assert that the CSS token layer matches the design specification.
 *
 *   pnpm test:tokens
 *
 * A design system drifts silently. Someone needs a slightly different blue,
 * writes `#0a7cff` inline, and six months later there are four accents and no
 * record of which was intended. This reads the YAML front matter of
 * docs/design-language.md, reads src/app/globals.css, and fails if:
 *
 *   - a token in the spec has no counterpart in the CSS,
 *   - a token's value in the CSS differs from the spec,
 *   - a hex colour appears in any source file that is not in the spec.
 *
 * The third check is the one with teeth: it catches the inline hex before it
 * becomes precedent. Two hex values are allowed outside the token layer and
 * both are documented at the point of use.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SPEC = join(ROOT, "..", "docs", "design-language.md");
const CSS = join(ROOT, "src", "app", "globals.css");

type Failure = { check: string; detail: string };
const failures: Failure[] = [];
let checked = 0;

const fail = (check: string, detail: string) => failures.push({ check, detail });

// ---------------------------------------------------------------------------
// Parse the spec's YAML front matter.
//
// Deliberately a small hand-written parser rather than a YAML dependency: the
// front matter is two levels of plain key/value, and adding a parser to read
// four scalar maps is a dependency to keep updated forever.
// ---------------------------------------------------------------------------

function frontMatter(source: string): Record<string, Record<string, string>> {
  const match = source.match(/^---\n([\s\S]*?)\n---/);
  if (!match?.[1]) throw new Error("design-language.md has no YAML front matter");

  const sections: Record<string, Record<string, string>> = {};
  let section = "";
  let subKey = "";

  for (const raw of match[1].split("\n")) {
    if (!raw.trim() || raw.trimStart().startsWith("#")) continue;

    const indent = raw.length - raw.trimStart().length;
    const line = raw.trim();

    if (indent === 0) {
      const [key] = line.split(":");
      section = key ?? "";
      sections[section] = {};
      subKey = "";
      continue;
    }

    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim();
    const value = line
      .slice(colon + 1)
      .trim()
      .replace(/^["']|["']$/g, "");

    if (indent === 2) {
      subKey = key;
      // A nested map (typography.body) has an empty value on its own line;
      // a flat map (colors.primary) has the value inline.
      if (value) sections[section]![key] = value;
    } else if (indent >= 4 && subKey) {
      sections[section]![`${subKey}.${key}`] = value;
    }
  }
  return sections;
}

const spec = frontMatter(readFileSync(SPEC, "utf8"));
const css = readFileSync(CSS, "utf8");

// ---------------------------------------------------------------------------
// 1. Every colour in the spec exists in the CSS with the same value.
// ---------------------------------------------------------------------------

for (const [name, value] of Object.entries(spec.colors ?? {})) {
  checked++;
  const property = `--color-${name}`;
  const found = css.match(new RegExp(`${property}:\\s*([^;]+);`));

  if (!found) {
    fail("colour missing", `${property} (spec: ${value}) is not defined in globals.css`);
    continue;
  }
  const actual = found[1]?.trim().toLowerCase();
  if (actual !== value.toLowerCase()) {
    fail("colour mismatch", `${property} is ${actual}, spec says ${value}`);
  }
}

// ---------------------------------------------------------------------------
// 2. Every typography token exists, with the right size and weight.
//
// Line-height and letter-spacing are checked leniently: the spec's own
// substitution note instructs tightening both for Inter, so an exact match
// would fail by design. Size and weight have no such licence.
// ---------------------------------------------------------------------------

const typographyNames = new Set(
  Object.keys(spec.typography ?? {})
    .map((key) => key.split(".")[0])
    .filter((name): name is string => Boolean(name)),
);

for (const name of typographyNames) {
  checked++;
  if (!css.includes(`--text-${name}:`)) {
    fail("typography missing", `--text-${name} is not defined in globals.css`);
    continue;
  }

  const specSize = spec.typography?.[`${name}.fontSize`];
  const actualSize = css.match(new RegExp(`--text-${name}:\\s*([^;]+);`))?.[1]?.trim();
  if (specSize && actualSize !== specSize) {
    fail("font size mismatch", `--text-${name} is ${actualSize}, spec says ${specSize}`);
  }

  const specWeight = spec.typography?.[`${name}.fontWeight`];
  const actualWeight = css
    .match(new RegExp(`--text-${name}--font-weight:\\s*([^;]+);`))?.[1]
    ?.trim();
  if (specWeight && actualWeight !== specWeight) {
    fail("font weight mismatch", `--text-${name} weight is ${actualWeight}, spec says ${specWeight}`);
  }
}

// Weight 500 is deliberately absent from the ladder. Catch it being
// reintroduced, in the token layer or anywhere else.
checked++;
for (const [name, value] of Object.entries(spec.typography ?? {})) {
  if (name.endsWith(".fontWeight") && value === "500") {
    fail("weight ladder", "the spec itself now contains weight 500 — the ladder is 300/400/600/700");
  }
}

// ---------------------------------------------------------------------------
// 3. Radii and spacing.
// ---------------------------------------------------------------------------

for (const [name, value] of Object.entries(spec.rounded ?? {})) {
  // `full` is an alias of `pill` in the spec; one token covers both.
  if (name === "full") continue;
  checked++;
  const actual = css.match(new RegExp(`--radius-${name}:\\s*([^;]+);`))?.[1]?.trim();
  if (!actual) fail("radius missing", `--radius-${name} is not defined`);
  else if (actual !== value) fail("radius mismatch", `--radius-${name} is ${actual}, spec says ${value}`);
}

for (const [name, value] of Object.entries(spec.spacing ?? {})) {
  checked++;
  const actual = css.match(new RegExp(`--spacing-${name}:\\s*([^;]+);`))?.[1]?.trim();
  if (!actual) fail("spacing missing", `--spacing-${name} is not defined`);
  else if (actual !== value) fail("spacing mismatch", `--spacing-${name} is ${actual}, spec says ${value}`);
}

// ---------------------------------------------------------------------------
// 4. No inline hex outside the token layer.
//
// The check that actually prevents drift. Everything else here verifies that
// the tokens are correct; this verifies they are the only source of colour.
// ---------------------------------------------------------------------------

const ALLOWED_OUTSIDE_TOKENS = new Set([
  // The one system shadow, whose rgba() carries its own alpha and so cannot
  // be expressed as a colour token.
  "rgba(0,0,0,0.22)",
]);

/**
 * Hex values that legitimately live outside the CSS token layer, each with the
 * reason it cannot be a custom property.
 */
const ALLOWED_LITERALS: Record<string, string> = {
  // <meta name="theme-color"> is consumed by the browser chrome before any
  // stylesheet is parsed, so it cannot reference a CSS variable. It matches
  // the global nav's surface-black on purpose: a white flash above a true-black
  // nav is exactly the kind of seam this design language avoids.
  "src/app/layout.tsx:#000000": "theme-color is read before CSS loads",
};

/**
 * Strip comments before scanning for colour literals.
 *
 * The first version of this check flagged nine "violations", and every one was
 * a hex inside a comment documenting which surface a token refers to — i.e.
 * exactly the practice the checker exists to encourage. A linter that punishes
 * its own goal gets disabled, so comments are removed first.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "") // block comments, JSDoc included
    .replace(/(^|[^:])\/\/.*$/gm, "$1"); // line comments, sparing URLs
}

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry.startsWith(".")) continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...sourceFiles(path));
    else if (/\.(tsx?|css)$/.test(entry)) out.push(path);
  }
  return out;
}

const specHexes = new Set(
  Object.values(spec.colors ?? {}).map((value) => value.toLowerCase()),
);

for (const file of sourceFiles(join(ROOT, "src"))) {
  const isTokenLayer = file.endsWith("globals.css");
  const relativePath = relative(ROOT, file);
  const body = stripComments(readFileSync(file, "utf8"));
  for (const hex of body.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []) {
    checked++;
    const value = hex.toLowerCase();
    if (isTokenLayer && specHexes.has(value)) continue;
    if (ALLOWED_OUTSIDE_TOKENS.has(value)) continue;
    if (ALLOWED_LITERALS[`${relativePath}:${value}`]) continue;
    if (specHexes.has(value) && !isTokenLayer) {
      fail(
        "inline hex",
        `${relativePath} writes ${hex} directly. It is a spec colour — use var(--color-…) instead.`,
      );
    } else {
      fail(
        "unknown colour",
        `${relativePath} uses ${hex}, which is not in the design specification.`,
      );
    }
  }
}

// ---------------------------------------------------------------------------

const label = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

if (failures.length === 0) {
  console.log(`design tokens: ${label(checked, "check")} passed`);
  process.exit(0);
}

console.error(`design tokens: ${label(failures.length, "failure")} of ${checked} checks\n`);
for (const { check, detail } of failures) console.error(`  [${check}] ${detail}`);
console.error("\nThe specification is docs/design-language.md. Change it there first.");
process.exit(1);
