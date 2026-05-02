"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Loader2, AlertCircle, Film } from "lucide-react";
import { getToken } from "@/lib/api/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type State =
  | { kind: "loading" }
  | { kind: "ok"; email: string; alreadyVerified: boolean }
  | { kind: "error"; code: string; message: string };

export default function VerifyPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setState({ kind: "error", code: "NO_TOKEN", message: "Missing token in URL." });
      return;
    }

    (async () => {
      try {
        const resp = await fetch(`${API_URL}/v1/auth/verify-email`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          const d = body?.detail ?? {};
          setState({
            kind: "error",
            code: d.code ?? "ERROR",
            message: d.message ?? "Verification failed.",
          });
          return;
        }
        const data = await resp.json();
        setState({ kind: "ok", email: data.email, alreadyVerified: data.already_verified });
      } catch {
        setState({ kind: "error", code: "NETWORK", message: "Network error." });
      }
    })();
  }, [params]);

  // Auto-advance on success — if already logged in, go straight to onboarding
  // (fresh registration flow); otherwise bounce to login with email prefilled.
  useEffect(() => {
    if (state.kind !== "ok") return;
    const t = setTimeout(() => {
      if (getToken()) {
        // Logged in → probably this is the same device they registered from.
        // Skip onboarding if already marked done; else the /onboarding guard handles it.
        router.replace("/onboarding");
      } else {
        const q = new URLSearchParams({ email: state.email, verified: "1" });
        router.replace(`/login?${q.toString()}`);
      }
    }, 1200);
    return () => clearTimeout(t);
  }, [state, router]);

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-8"
      style={{ backgroundColor: "var(--background)" }}
    >
      <div
        className="w-full max-w-sm rounded-xl p-8 flex flex-col items-center gap-4 text-center"
        style={{
          backgroundColor: "var(--card)",
          borderWidth: 1,
          borderColor: "var(--border)",
        }}
      >
        <Film className="h-8 w-8" style={{ color: "var(--tab-collaborative)" }} />

        {state.kind === "loading" && (
          <>
            <Loader2
              className="h-10 w-10 animate-spin"
              style={{ color: "var(--muted-foreground)" }}
            />
            <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              Verifying your email…
            </h1>
          </>
        )}

        {state.kind === "ok" && (
          <>
            <CheckCircle2 className="h-12 w-12" style={{ color: "oklch(0.7 0.18 145)" }} />
            <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              {state.alreadyVerified
                ? "Email already verified"
                : "Email verified!"}
            </h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              {state.email}
            </p>
            <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
              Redirecting…
            </p>
          </>
        )}

        {state.kind === "error" && (
          <>
            <AlertCircle className="h-12 w-12" style={{ color: "var(--destructive)" }} />
            <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              Verification failed
            </h1>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              {state.message}
            </p>
            <Link
              href="/login"
              className="text-sm font-medium underline"
              style={{ color: "var(--tab-collaborative)" }}
            >
              Back to login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
