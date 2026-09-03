"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { FloatingNav, NavPill } from "@/components/ui/floating-nav";
import { Claim, Eyebrow, Section } from "@/components/ui/product";
import { api, ApiError, type PublicUser } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Sign in, and register from the same form.
 *
 * One form with a mode toggle rather than two pages: the fields are almost
 * identical, and two routes means two places for the error handling and the
 * redirect to drift apart.
 */
export default function SignInPage() {
  // useSearchParams needs a Suspense boundary above it in the App Router.
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}

function SignInForm() {
  const router = useRouter();
  const { refresh } = useAuth();
  // Where RequireAuth sent us from, so a bounced visitor lands back there.
  const next = useSearchParams().get("next") ?? "/library";
  const [mode, setMode] = useState<"sign-in" | "register">("sign-in");
  const [email, setEmail] = useState("demo@recall.study");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<PublicUser | null>(null);
  const [busy, setBusy] = useState(false);

  const registering = mode === "register";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = registering
        ? await api.register(email, password, displayName)
        : await api.login(email, password);
      setUser(result);
      // A moment on the confirmation before moving, so the name that came back
      // from the server is actually readable. Redirecting instantly makes a
      // successful sign-in indistinguishable from a page reload.
      await refresh();
      setTimeout(() => router.push(next.startsWith("/") ? next : "/library"), 900);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <FloatingNav title="Sign in">
        <NavPill href="/" variant="pearl">
          Overview
        </NavPill>
      </FloatingNav>

      <Section tall>
        <Eyebrow>{registering ? "Create an account" : "Welcome back"}</Eyebrow>
        <Claim>{registering ? "Start with your own notes." : "Sign in to Recall."}</Claim>

        {user ? (
          <p className="mx-auto mt-xxl max-w-[30ch] text-center text-lead-copy text-ink">
            Signed in as {user.display_name}. Taking you to your library…
          </p>
        ) : (
          <form onSubmit={submit} className="mx-auto mt-xxl flex w-full max-w-[380px] flex-col gap-sm">
            {registering ? (
              <Field
                label="Name"
                type="text"
                value={displayName}
                onChange={setDisplayName}
                autoComplete="name"
                required
              />
            ) : null}

            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              autoComplete="email"
              required
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              // The browser needs to know which one this is, or it offers to
              // save the wrong thing and autofills the wrong field.
              autoComplete={registering ? "new-password" : "current-password"}
              required
              hint={registering ? "At least 12 characters. No symbol requirements." : undefined}
            />

            {error ? (
              // role=alert so a screen reader announces the failure rather than
              // leaving the user pressing a button that appears to do nothing.
              <p role="alert" className="text-caption text-ink">
                {error}
              </p>
            ) : null}

            <Button type="submit" variant="primary" disabled={busy} className="mt-sm w-full">
              {busy ? "One moment…" : registering ? "Create account" : "Sign in"}
            </Button>

            <button
              type="button"
              onClick={() => {
                setMode(registering ? "sign-in" : "register");
                setError(null);
              }}
              className="mt-xs cursor-pointer border-0 bg-transparent text-caption text-primary"
            >
              {registering ? "I already have an account" : "Create an account instead"}
            </button>
          </form>
        )}

        {!user && !registering ? (
          <p className="mx-auto mt-section max-w-[40ch] text-center text-caption text-ink-muted-48">
            Trying this out? Sign in with <span className="text-ink">demo@recall.study</span> and{" "}
            <span className="text-ink">study-out-loud-2026</span>. The account is seeded by{" "}
            <Link href="https://github.com/ezitounioussama/recall-study-assistant/blob/main/api/app/seed.py">
              api/app/seed.py
            </Link>
            .
          </p>
        ) : null}
      </Section>
    </>
  );
}

/**
 * A labelled input at the spec's pill radius and 44px height. The search input
 * in the design language is a pill, and the CTA grammar is a pill, so a form
 * field that is a rounded rectangle would be the only one of its kind.
 */
function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
  required,
  hint,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  required?: boolean;
  hint?: string;
}) {
  const id = `field-${label.toLowerCase()}`;
  return (
    <div className="flex flex-col gap-xxs">
      <label htmlFor={id} className="text-caption text-ink-muted-48">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={hint ? `${id}-hint` : undefined}
        className="h-11 rounded-pill border border-hairline bg-canvas px-lg text-body text-ink"
      />
      {hint ? (
        <p id={`${id}-hint`} className="text-fine-print text-ink-muted-48">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
