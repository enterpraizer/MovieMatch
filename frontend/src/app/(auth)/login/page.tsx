"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Film, Mail, Eye, EyeOff, Loader2, CheckCircle2, Apple } from "lucide-react";
import { setTokens } from "@/lib/api/client";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefilledEmail = searchParams.get("email") ?? "";
  const justVerified = searchParams.get("verified") === "1";
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [passwordFocus, setPasswordFocus] = useState(false);

  const {
    register,
    handleSubmit,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: prefilledEmail, password: "" },
  });

  // When we come from /verify, the email is already correct — shift focus to
  // the password so the user's next keystroke lands there.
  useEffect(() => {
    if (prefilledEmail && !passwordFocus) {
      setFocus("password");
      setPasswordFocus(true);
    }
  }, [prefilledEmail, setFocus, passwordFocus]);

  const onSubmit = async (data: LoginForm) => {
    setFormError(null);
    try {
      const resp = await fetch(`${API_URL}/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (resp.status === 401) {
        setFormError("Invalid email or password");
        return;
      }
      if (!resp.ok) {
        setFormError("Connection error. Please try again.");
        return;
      }

      const tokens = await resp.json();
      setTokens(tokens.access_token, tokens.refresh_token);
      router.push("/");
    } catch {
      setFormError("Connection error. Please try again.");
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ backgroundColor: "var(--background)" }}
    >
      <div
        className="w-full max-w-sm rounded-xl p-6"
        style={{
          backgroundColor: "var(--card)",
          borderWidth: 1,
          borderColor: "var(--border)",
        }}
      >
        {/* Brand */}
        <div className="flex flex-col items-center gap-2 mb-6">
          <Film className="h-8 w-8" style={{ color: "var(--tab-collaborative)" }} />
          <h1 className="text-xl font-bold" style={{ color: "var(--foreground)" }}>
            Movie<span style={{ color: "var(--tab-collaborative)" }}>Match</span>
          </h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            Sign in to your account
          </p>
        </div>

        {justVerified && (
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-4"
            style={{
              backgroundColor: "oklch(0.22 0.06 145)",
              color: "oklch(0.85 0.15 145)",
            }}
          >
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            Email verified — enter your password to continue.
          </div>
        )}

        {/* Sign in with Apple (placeholder). Enabling requires an Apple
            Developer Program membership + Services ID + signed client JWT. */}
        <button
          type="button"
          disabled
          title="Coming soon — Apple Sign-In setup pending"
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold mb-3 cursor-not-allowed opacity-60"
          style={{
            backgroundColor: "#000",
            color: "white",
            borderWidth: 1,
            borderColor: "var(--border)",
          }}
        >
          <Apple className="h-4 w-4" />
          Continue with Apple
          <span className="text-[10px] opacity-60 ml-1">(soon)</span>
        </button>

        <div className="flex items-center gap-2 mb-3">
          <div className="flex-1 h-px" style={{ backgroundColor: "var(--border)" }} />
          <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            or
          </span>
          <div className="flex-1 h-px" style={{ backgroundColor: "var(--border)" }} />
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          {/* Email */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Email
            </label>
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-lg"
              style={{
                backgroundColor: "var(--secondary)",
                borderWidth: 1,
                borderColor: errors.email ? "var(--destructive)" : "var(--border)",
              }}
            >
              <Mail className="h-4 w-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
              <input
                {...register("email")}
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: "var(--foreground)" }}
              />
            </div>
            {errors.email && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {errors.email.message}
              </p>
            )}
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Password
            </label>
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-lg"
              style={{
                backgroundColor: "var(--secondary)",
                borderWidth: 1,
                borderColor: errors.password ? "var(--destructive)" : "var(--border)",
              }}
            >
              <input
                {...register("password")}
                type={showPassword ? "text" : "password"}
                placeholder="Your password"
                autoComplete="current-password"
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: "var(--foreground)" }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="shrink-0"
                tabIndex={-1}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
                ) : (
                  <Eye className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
                )}
              </button>
            </div>
            {errors.password && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Form error */}
          {formError && (
            <div
              className="px-3 py-2 rounded-lg text-sm"
              style={{
                backgroundColor: "oklch(0.22 0.06 25)",
                color: "oklch(0.8 0.15 25)",
              }}
            >
              {formError}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-60"
            style={{ backgroundColor: "var(--tab-collaborative)" }}
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs" style={{ color: "var(--muted-foreground)" }}>
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="font-medium underline"
            style={{ color: "var(--tab-collaborative)" }}
          >
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
