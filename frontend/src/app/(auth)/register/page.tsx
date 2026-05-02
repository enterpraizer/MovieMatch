"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Film, Loader2, Apple, Mail, CheckCircle2 } from "lucide-react";
import { setTokens } from "@/lib/api/client";
import { useRatingsStore } from "@/store/ratings-store";

const registerSchema = z
  .object({
    display_name: z.string().min(2, "At least 2 characters").max(100),
    email: z.string().email("Enter a valid email"),
    password: z
      .string()
      .min(8, "At least 8 characters")
      .max(100)
      .regex(/[A-Z]/, "Include an uppercase letter")
      .regex(/\d/, "Include a digit"),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof registerSchema>;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function PasswordStrength({ password }: { password: string }) {
  const { label, percent, color } = useMemo(() => {
    if (password.length === 0) return { label: "", percent: 0, color: "transparent" };
    if (password.length < 8)
      return { label: "Weak", percent: 25, color: "var(--destructive)" };
    const hasUpper = /[A-Z]/.test(password);
    const hasDigit = /\d/.test(password);
    if (hasUpper && hasDigit)
      return { label: "Strong", percent: 100, color: "oklch(0.65 0.2 145)" };
    return { label: "Medium", percent: 60, color: "oklch(0.75 0.15 85)" };
  }, [password]);

  if (!password) return null;

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ backgroundColor: "var(--secondary)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${percent}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs" style={{ color }}>
        {label}
      </span>
    </div>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const [resendState, setResendState] = useState<"idle" | "busy" | "sent">("idle");

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const password = watch("password", "");

  const onSubmit = async (data: RegisterForm) => {
    setFormError(null);
    try {
      const resp = await fetch(`${API_URL}/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: data.email,
          password: data.password,
          display_name: data.display_name,
        }),
      });

      if (resp.status === 409) {
        setFormError("This email is already registered.");
        return;
      }
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setFormError(body?.error?.message ?? "Registration failed. Try again.");
        return;
      }

      const tokens = await resp.json();
      // Fresh account — wipe every leftover from a previous session in this
      // browser before storing new tokens, otherwise Zustand's localStorage
      // persist would hydrate the new user's store with the prior user's
      // ratings and push them back to the server on first load.
      if (typeof window !== "undefined") {
        const prefixes = ["mm-", "mm_"];
        for (const k of Object.keys(window.localStorage)) {
          if (prefixes.some((p) => k.startsWith(p))) window.localStorage.removeItem(k);
        }
        for (const k of Object.keys(window.sessionStorage)) {
          if (prefixes.some((p) => k.startsWith(p))) window.sessionStorage.removeItem(k);
        }
      }
      useRatingsStore.setState({ ratings: {} });
      setTokens(tokens.access_token, tokens.refresh_token);
      setRegisteredEmail(data.email);
    } catch {
      setFormError("Connection error. Please try again.");
    }
  };

  const inputStyle = (hasError: boolean) => ({
    backgroundColor: "var(--secondary)",
    borderWidth: 1,
    borderColor: hasError ? "var(--destructive)" : "var(--border)",
  });

  const resend = async () => {
    if (!registeredEmail) return;
    setResendState("busy");
    try {
      await fetch(`${API_URL}/v1/auth/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: registeredEmail }),
      });
      setResendState("sent");
    } catch {
      setResendState("idle");
    }
  };

  if (registeredEmail) {
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
          <Mail className="h-10 w-10" style={{ color: "var(--tab-collaborative)" }} />
          <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
            Check your inbox
          </h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            We sent a verification link to{" "}
            <strong style={{ color: "var(--foreground)" }}>{registeredEmail}</strong>.
            Click it to activate your account and start rating movies.
          </p>
          <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            Didn&apos;t get it? Check spam, or resend below. In dev mode the link is printed to the backend log.
          </p>
          {resendState === "sent" ? (
            <p
              className="flex items-center gap-1.5 text-xs font-medium"
              style={{ color: "oklch(0.7 0.18 145)" }}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              New link sent.
            </p>
          ) : (
            <button
              type="button"
              onClick={resend}
              disabled={resendState === "busy"}
              className="text-xs font-medium underline disabled:opacity-50"
              style={{ color: "var(--tab-collaborative)" }}
            >
              {resendState === "busy" ? "Sending…" : "Resend email"}
            </button>
          )}
          <Link
            href="/login"
            className="mt-2 text-xs"
            style={{ color: "var(--muted-foreground)" }}
          >
            Already verified? Sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-8"
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
        <div className="flex flex-col items-center gap-2 mb-6">
          <Film className="h-8 w-8" style={{ color: "var(--tab-collaborative)" }} />
          <h1 className="text-xl font-bold" style={{ color: "var(--foreground)" }}>
            Create your account
          </h1>
        </div>

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
            or sign up with email
          </span>
          <div className="flex-1 h-px" style={{ backgroundColor: "var(--border)" }} />
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          {/* Display name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Display name
            </label>
            <input
              {...register("display_name")}
              placeholder="Your name"
              autoComplete="name"
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{
                ...inputStyle(!!errors.display_name),
                color: "var(--foreground)",
              }}
            />
            {errors.display_name && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {errors.display_name.message}
              </p>
            )}
          </div>

          {/* Email */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Email
            </label>
            <input
              {...register("email")}
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{
                ...inputStyle(!!errors.email),
                color: "var(--foreground)",
              }}
            />
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
            <input
              {...register("password")}
              type="password"
              placeholder="Min 8 chars, uppercase + digit"
              autoComplete="new-password"
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{
                ...inputStyle(!!errors.password),
                color: "var(--foreground)",
              }}
            />
            <PasswordStrength password={password} />
            {errors.password && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Confirm password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Confirm password
            </label>
            <input
              {...register("confirmPassword")}
              type="password"
              placeholder="Re-enter password"
              autoComplete="new-password"
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{
                ...inputStyle(!!errors.confirmPassword),
                color: "var(--foreground)",
              }}
            />
            {errors.confirmPassword && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {errors.confirmPassword.message}
              </p>
            )}
          </div>

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

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-60"
            style={{ backgroundColor: "var(--tab-collaborative)" }}
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs" style={{ color: "var(--muted-foreground)" }}>
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium underline"
            style={{ color: "var(--tab-collaborative)" }}
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
