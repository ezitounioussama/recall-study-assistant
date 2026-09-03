"use client";

/**
 * The app's chrome: a thin bar with the wordmark and who is signed in, and
 * the dock — the macOS-style island at the bottom that is the app's whole
 * navigation. Three places and a way out.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { Dock, DockIcon } from "@/components/magicui/dock";
import { AskIcon, LibraryIcon, ReviewIcon, SignOutIcon } from "@/components/app/icons";
import { RequireAuth, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const PLACES = [
  { href: "/library", label: "Library", Icon: LibraryIcon },
  { href: "/chat", label: "Ask", Icon: AskIcon },
  { href: "/review", label: "Review", Icon: ReviewIcon },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <RequireAuth>
      <header className="sticky top-0 z-50 h-11 bg-canvas/80 backdrop-blur-xl">
        <div className="mx-auto flex h-full w-full max-w-[1200px] items-center justify-between px-lg">
          <Link href="/" className="text-nav-link font-semibold text-ink">
            Recall
          </Link>
          <span className="text-caption text-lead-grey">{user?.display_name}</span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] px-lg pt-xl pb-[160px]">{children}</main>

      <nav aria-label="App" className="pointer-events-none fixed inset-x-0 bottom-lg z-50 flex justify-center px-lg">
        <div className="pointer-events-auto">
          <Dock iconSize={48} iconMagnification={66} iconDistance={120}>
            {PLACES.map(({ href, label, Icon }) => {
              const active = pathname.startsWith(href);
              return (
                <DockIcon key={href} aria-label={label} title={label} onClick={() => router.push(href)} className={cn(active ? "bg-canvas-parchment text-primary" : "text-ink")}>
                  <Icon className="size-[60%]" />
                </DockIcon>
              );
            })}
            <span aria-hidden className="mx-xxs h-8 w-px bg-hairline" />
            <DockIcon
              aria-label="Sign out"
              title="Sign out"
              className="text-lead-grey"
              onClick={async () => {
                await signOut();
                router.push("/");
              }}
            >
              <SignOutIcon className="size-[60%]" />
            </DockIcon>
          </Dock>
        </div>
      </nav>
    </RequireAuth>
  );
}
