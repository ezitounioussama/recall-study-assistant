"use client";

/**
 * Who is signed in, for the whole app. One `/auth/me` on mount; the cookie
 * does the rest. Pages that need a user render `<RequireAuth>` and get sent
 * to /sign-in (and back) when there is none.
 */
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, type PublicUser } from "@/lib/api";

type AuthState = {
  user: PublicUser | null;
  loading: boolean;
  /** Re-read /auth/me — after a sign-in, for instance. */
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(
    () =>
      api
        .me()
        .then(setUser)
        .catch((error: unknown) => {
          if (error instanceof ApiError && error.status !== 401) console.warn(error.message);
          setUser(null);
        })
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, refresh, signOut }), [user, loading, refresh, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace(`/sign-in?next=${encodeURIComponent(pathname)}`);
  }, [loading, user, router, pathname]);

  if (loading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-body text-lead-grey" aria-busy>
        {loading ? "Checking your session…" : "Redirecting to sign in…"}
      </div>
    );
  }
  return <>{children}</>;
}
