"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Image from "next/image";
import {
  ArrowLeft,
  Loader2,
  Mail,
  Calendar,
  Star,
  Film,
  LogOut,
  KeyRound,
  Trash2,
  AlertTriangle,
  Pencil,
  Bookmark,
  X,
  ChevronDown,
} from "lucide-react";
import { api, clearTokens, getToken } from "@/lib/api/client";
import { BackButton } from "@/components/common/BackButton";
import { useRatingsStore } from "@/store/ratings-store";

function wipeLocalUserState() {
  if (typeof window === "undefined") return;
  // Blow away all mm-prefixed keys (Zustand persists, session caches, flags).
  const prefixes = ["mm-", "mm_"];
  for (const k of Object.keys(window.localStorage)) {
    if (prefixes.some((p) => k.startsWith(p))) window.localStorage.removeItem(k);
  }
  for (const k of Object.keys(window.sessionStorage)) {
    if (prefixes.some((p) => k.startsWith(p))) window.sessionStorage.removeItem(k);
  }
  // Reset Zustand's in-memory state too — localStorage alone won't clear the
  // running store until a full reload.
  useRatingsStore.setState({ ratings: {} });
}

type UserInfo = {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  created_at: string;
  last_login_at: string | null;
};

type WatchlistMovie = {
  id: number;
  title: string;
  year: number | null;
  poster_url: string | null;
  genres: string[];
  avg_rating: number | null;
};

type GenreCount = { slug: string; name: string; count: number };

type UserStats = {
  total_ratings: number;
  avg_rating: number | null;
  first_rated_at: string | null;
  last_rated_at: string | null;
  top_genres: GenreCount[];
  score_distribution: Record<string, number>;
};

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z
      .string()
      .min(8, "At least 8 characters")
      .max(100)
      .regex(/[A-Z]/, "Include an uppercase letter")
      .regex(/\d/, "Include a digit"),
    confirm_new_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_new_password, {
    message: "Passwords don't match",
    path: ["confirm_new_password"],
  });

type PasswordForm = z.infer<typeof passwordSchema>;

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    const ms = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days} d ago`;
    return formatDate(iso);
  } catch {
    return iso;
  }
}

const inputStyle = (hasError: boolean) => ({
  backgroundColor: "var(--secondary)",
  borderWidth: 1,
  borderColor: hasError ? "var(--destructive)" : "var(--border)",
});

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistMovie[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        // Core: user info. If this fails the whole page is unusable.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const u = await (api as any).GET("/v1/auth/me");
        if (cancelled) return;
        if (u.error || !u.data) {
          setError("Couldn't load your profile. Try again.");
          return;
        }
        setUser(u.data as UserInfo);
        // Optional: stats + watchlist. A failure here should NOT block the
        // profile from rendering — just show empty sections.
        const [s, w] = await Promise.allSettled([
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (api as any).GET("/v1/auth/me/stats"),
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (api as any).GET("/v1/watchlist"),
        ]);
        if (cancelled) return;
        if (s.status === "fulfilled" && s.value.data) {
          setStats(s.value.data as UserStats);
        }
        if (w.status === "fulfilled" && w.value.data) {
          setWatchlist(w.value.data as WatchlistMovie[]);
        }
      } catch (e) {
        if (!cancelled) {
          console.error("profile load failed", e);
          setError("Couldn't reach the server. Check your connection and retry.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, reloadKey]);

  const removeWatchlist = async (movieId: number) => {
    setWatchlist((prev) => prev.filter((m) => m.id !== movieId));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (api as any).DELETE(`/v1/watchlist/${movieId}`);
  };

  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ backgroundColor: "var(--background)" }}
      >
        <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--muted-foreground)" }} />
      </div>
    );
  }

  if (error || !user) {
    return (
      <div
        className="min-h-screen flex items-center justify-center p-4"
        style={{ backgroundColor: "var(--background)" }}
      >
        <div
          className="rounded-xl p-6 max-w-sm text-center flex flex-col gap-3"
          style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
        >
          <p style={{ color: "var(--destructive)" }}>{error ?? "Not authenticated"}</p>
          <div className="flex gap-2 justify-center">
            <button
              type="button"
              onClick={() => setReloadKey((k) => k + 1)}
              className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
              style={{ backgroundColor: "var(--tab-collaborative)" }}
            >
              Retry
            </button>
            <Link
              href="/"
              className="px-4 py-1.5 rounded-lg text-sm font-medium"
              style={{
                backgroundColor: "transparent",
                borderWidth: 1,
                borderColor: "var(--border)",
                color: "var(--foreground)",
              }}
            >
              Go home
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const initial = (user.display_name || user.email)[0]?.toUpperCase() ?? "?";

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      <header
        className="sticky top-0 z-10 backdrop-blur-lg"
        style={{
          backgroundColor: "oklch(0.13 0.005 260 / 0.9)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <BackButton
            fallbackHref="/"
            className="flex items-center gap-1 text-sm px-2 py-1 rounded-lg transition-colors cursor-pointer"
            style={{ color: "var(--muted-foreground)" }}
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </BackButton>
          <h1 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Profile
          </h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-4">
        <ProfileHeader user={user} initial={initial} onSaved={setUser} />
        <StatsCard stats={stats} />
        <RatingHistoryCard />
        <WatchlistCard movies={watchlist} onRemove={removeWatchlist} />
        <ChangePasswordCard />
        <DangerZone />
      </main>
    </div>
  );
}

interface RatedItem {
  movie_id: number;
  title: string | null;
  year: number | null;
  poster_url: string | null;
  score: number;
  updated_at: string | null;
}

function RatingHistoryCard() {
  const [items, setItems] = useState<RatedItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const resp = await (api as any).GET("/v1/ratings/me", {
          params: { query: { limit: 50 } },
        });
        if (cancelled) return;
        const data = resp.data;
        const arr: RatedItem[] = Array.isArray(data)
          ? (data as RatedItem[])
          : ((data as { items?: RatedItem[] })?.items ?? []);
        setItems(arr);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <CollapsibleSection
      storageKey="history"
      defaultCollapsed
      icon={<Star className="h-4 w-4" />}
      title="Rating history"
      badge={
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ backgroundColor: "var(--secondary)", color: "var(--muted-foreground)" }}
        >
          {items.length}
        </span>
      }
    >
      {loading ? (
        <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
          Loading…
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
          You haven&apos;t rated any movies yet.
        </p>
      ) : (
        <ul className="flex flex-col divide-y" style={{ borderColor: "var(--border)" }}>
          {items.map((r) => (
            <li key={r.movie_id} className="py-2 flex items-center gap-3">
              <Link href={`/movies/${r.movie_id}`} className="flex items-center gap-3 flex-1 min-w-0">
                {r.poster_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={r.poster_url}
                    alt=""
                    className="h-12 w-8 rounded object-cover shrink-0"
                    style={{ backgroundColor: "var(--secondary)" }}
                  />
                ) : (
                  <div
                    className="h-12 w-8 rounded shrink-0 flex items-center justify-center"
                    style={{ backgroundColor: "var(--secondary)" }}
                  >
                    <Film className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
                  </div>
                )}
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-sm truncate" style={{ color: "var(--foreground)" }}>
                    {r.title ?? `Movie #${r.movie_id}`}
                  </span>
                  <span className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>
                    {r.year ?? ""}
                    {r.updated_at && ` · ${formatDate(r.updated_at)}`}
                  </span>
                </div>
              </Link>
              <div className="flex items-center gap-1 shrink-0 tabular-nums">
                <Star
                  className="h-3.5 w-3.5"
                  style={{ fill: "var(--accent)", color: "var(--accent)" }}
                />
                <span className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
                  {r.score.toFixed(1)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </CollapsibleSection>
  );
}

function ProfileHeader({
  user,
  initial,
  onSaved,
}: {
  user: UserInfo;
  initial: string;
  onSaved: (u: UserInfo) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [avatarUrl, setAvatarUrl] = useState(user.avatar_url ?? "");
  const [bio, setBio] = useState(user.bio ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resp = await (api as any).PATCH("/v1/auth/me", {
        body: {
          display_name: displayName.trim() || null,
          avatar_url: avatarUrl.trim() || null,
          bio: bio.trim() || null,
        },
      });
      if (resp.error || !resp.data) {
        setErr("Couldn't save changes.");
        return;
      }
      onSaved(resp.data as UserInfo);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="rounded-xl p-6 flex flex-col gap-4"
      style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
    >
      <div className="flex items-start gap-4">
        {user.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.avatar_url}
            alt=""
            className="h-16 w-16 rounded-full object-cover"
            style={{ backgroundColor: "var(--secondary)" }}
          />
        ) : (
          <div
            className="h-16 w-16 rounded-full flex items-center justify-center text-2xl font-semibold shrink-0"
            style={{ backgroundColor: "var(--tab-collaborative)", color: "white" }}
            aria-hidden
          >
            {initial}
          </div>
        )}
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h2 className="text-lg font-semibold truncate" style={{ color: "var(--foreground)" }}>
            {user.display_name ?? "Unnamed"}
          </h2>
          <div className="flex items-center gap-1.5 text-sm" style={{ color: "var(--muted-foreground)" }}>
            <Mail className="h-3.5 w-3.5" />
            <span className="truncate">{user.email}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: "var(--muted-foreground)" }}>
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              Joined {formatDate(user.created_at)}
            </span>
            {user.last_login_at && (
              <span>Last active {formatRelative(user.last_login_at)}</span>
            )}
          </div>
          {user.bio && !editing && (
            <p className="text-sm mt-2 whitespace-pre-line" style={{ color: "var(--foreground)" }}>
              {user.bio}
            </p>
          )}
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            aria-label="Edit profile"
            className="shrink-0 flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-lg text-sm font-medium"
            style={{
              backgroundColor: "transparent",
              borderWidth: 1,
              borderColor: "var(--border)",
              color: "var(--foreground)",
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Edit</span>
          </button>
        )}
      </div>

      {editing && (
        <div className="flex flex-col gap-3 pt-2 border-t" style={{ borderColor: "var(--border)" }}>
          <Field label="Display name">
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{ ...inputStyle(false), color: "var(--foreground)" }}
            />
          </Field>
          <Field label="Avatar URL">
            <input
              value={avatarUrl}
              onChange={(e) => setAvatarUrl(e.target.value)}
              placeholder="https://..."
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{ ...inputStyle(false), color: "var(--foreground)" }}
            />
          </Field>
          <Field label="Bio">
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={3}
              maxLength={500}
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none resize-none"
              style={{ ...inputStyle(false), color: "var(--foreground)" }}
            />
          </Field>
          {err && (
            <p className="text-xs" style={{ color: "var(--destructive)" }}>
              {err}
            </p>
          )}
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={busy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white disabled:opacity-60"
              style={{ backgroundColor: "var(--tab-collaborative)" }}
            >
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setDisplayName(user.display_name ?? "");
                setAvatarUrl(user.avatar_url ?? "");
                setBio(user.bio ?? "");
                setErr(null);
              }}
              className="px-3 py-1.5 rounded-lg text-sm"
              style={{
                backgroundColor: "transparent",
                borderWidth: 1,
                borderColor: "var(--border)",
                color: "var(--foreground)",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function WatchlistCard({
  movies,
  onRemove,
}: {
  movies: WatchlistMovie[];
  onRemove: (id: number) => void;
}) {
  return (
    <CollapsibleSection
      storageKey="watchlist"
      icon={<Bookmark className="h-4 w-4" />}
      title="Watchlist"
      badge={
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ backgroundColor: "var(--secondary)", color: "var(--muted-foreground)" }}
        >
          {movies.length}
        </span>
      }
    >
      {movies.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
          Nothing saved yet. Add movies from their details page.
        </p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {movies.map((m) => (
            <li
              key={m.id}
              className="relative rounded-lg overflow-hidden group"
              style={{ backgroundColor: "var(--secondary)" }}
            >
              <Link href={`/movies/${m.id}`} className="block">
                <div className="aspect-[2/3] relative">
                  {m.poster_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={m.poster_url}
                      alt={m.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Film className="h-8 w-8" style={{ color: "var(--muted-foreground)" }} />
                    </div>
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs font-medium truncate" style={{ color: "var(--foreground)" }}>
                    {m.title}
                  </p>
                  <p className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>
                    {m.year ?? ""}
                    {m.avg_rating !== null && ` · ★ ${m.avg_rating.toFixed(1)}`}
                  </p>
                </div>
              </Link>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  onRemove(m.id);
                }}
                aria-label="Remove from watchlist"
                className="absolute top-1 right-1 p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ backgroundColor: "oklch(0.18 0.008 260 / 0.85)" }}
              >
                <X className="h-3.5 w-3.5" style={{ color: "white" }} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </CollapsibleSection>
  );
}

function StatsCard({ stats }: { stats: UserStats | null }) {
  if (!stats || stats.total_ratings === 0) {
    return (
      <CollapsibleSection
        storageKey="activity"
        icon={<Star className="h-4 w-4" />}
        title="Your activity"
      >
        <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
          You haven&apos;t rated any movies yet.{" "}
          <Link
            href="/"
            className="underline"
            style={{ color: "var(--tab-collaborative)" }}
          >
            Rate some movies
          </Link>{" "}
          to see stats.
        </p>
      </CollapsibleSection>
    );
  }

  const scoreKeys = Object.keys(stats.score_distribution).sort(
    (a, b) => parseFloat(a) - parseFloat(b),
  );
  const maxScoreCount = Math.max(...Object.values(stats.score_distribution), 1);
  const maxGenreCount = stats.top_genres[0]?.count ?? 1;

  return (
    <CollapsibleSection
      storageKey="activity"
      icon={<Star className="h-4 w-4" />}
      title="Your activity"
      badge={
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ backgroundColor: "var(--secondary)", color: "var(--muted-foreground)" }}
        >
          {stats.total_ratings}
        </span>
      }
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile
          icon={<Film className="h-4 w-4" />}
          label="Ratings"
          value={String(stats.total_ratings)}
        />
        <StatTile
          icon={<Star className="h-4 w-4" />}
          label="Avg score"
          value={stats.avg_rating?.toFixed(2) ?? "—"}
        />
        <StatTile
          icon={<Calendar className="h-4 w-4" />}
          label="First"
          value={formatDate(stats.first_rated_at)}
        />
        <StatTile
          icon={<Calendar className="h-4 w-4" />}
          label="Latest"
          value={formatDate(stats.last_rated_at)}
        />
      </div>

      {stats.top_genres.length >= 3 && (
        <GenreRadar genres={stats.top_genres.slice(0, 8)} />
      )}

      {stats.top_genres.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--muted-foreground)" }}>
            Top genres
          </h4>
          <div className="flex flex-col gap-1.5">
            {stats.top_genres.map((g) => (
              <div key={g.slug} className="flex items-center gap-3">
                <span className="text-sm w-28 truncate" style={{ color: "var(--foreground)" }}>
                  {g.name}
                </span>
                <div
                  className="flex-1 h-2 rounded-full overflow-hidden"
                  style={{ backgroundColor: "var(--secondary)" }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(g.count / maxGenreCount) * 100}%`,
                      backgroundColor: "var(--tab-collaborative)",
                    }}
                  />
                </div>
                <span className="text-xs tabular-nums w-10 text-right" style={{ color: "var(--muted-foreground)" }}>
                  {g.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {scoreKeys.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--muted-foreground)" }}>
            Rating distribution
          </h4>
          <div className="flex items-end gap-1 h-28">
            {scoreKeys.map((k) => {
              const cnt = stats.score_distribution[k];
              const h = (cnt / maxScoreCount) * 100;
              return (
                <div key={k} className="flex-1 flex flex-col items-center gap-1 justify-end">
                  <div
                    className="w-full rounded-t-sm"
                    style={{
                      height: `${Math.max(h, 3)}%`,
                      backgroundColor: "var(--tab-collaborative)",
                      opacity: 0.3 + (parseFloat(k) / 5) * 0.7,
                    }}
                    title={`${k}: ${cnt}`}
                  />
                  <span className="text-[10px] tabular-nums" style={{ color: "var(--muted-foreground)" }}>
                    {parseFloat(k).toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}

function GenreRadar({ genres }: { genres: GenreCount[] }) {
  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 24;
  const n = genres.length;
  const max = Math.max(...genres.map((g) => g.count), 1);

  const points = genres.map((g, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const r = (g.count / max) * radius;
    const anchor: "start" | "end" | "middle" =
      Math.cos(angle) > 0.2 ? "start" : Math.cos(angle) < -0.2 ? "end" : "middle";
    return {
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      labelX: cx + Math.cos(angle) * (radius + 14),
      labelY: cy + Math.sin(angle) * (radius + 14),
      labelAnchor: anchor,
      name: g.name,
    };
  });

  const pathD =
    points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ") + " Z";

  const rings = [0.25, 0.5, 0.75, 1.0];

  return (
    <div className="flex flex-col gap-2">
      <h4
        className="text-xs font-medium uppercase tracking-wide"
        style={{ color: "var(--muted-foreground)" }}
      >
        Taste radar
      </h4>
      <div className="flex justify-center">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label="Genre radar chart"
        >
          {rings.map((r) => (
            <circle
              key={r}
              cx={cx}
              cy={cy}
              r={radius * r}
              fill="none"
              stroke="var(--border)"
              strokeWidth="1"
              opacity="0.4"
            />
          ))}
          {points.map((p, i) => (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + (p.x - cx) * (radius / Math.max(1, Math.hypot(p.x - cx, p.y - cy)))}
              y2={cy + (p.y - cy) * (radius / Math.max(1, Math.hypot(p.x - cx, p.y - cy)))}
              stroke="var(--border)"
              strokeWidth="1"
              opacity="0.25"
            />
          ))}
          <path
            d={pathD}
            fill="var(--tab-collaborative)"
            fillOpacity="0.25"
            stroke="var(--tab-collaborative)"
            strokeWidth="1.5"
          />
          {points.map((p, i) => (
            <circle
              key={`p-${i}`}
              cx={p.x}
              cy={p.y}
              r="3"
              fill="var(--tab-collaborative)"
            />
          ))}
          {points.map((p, i) => (
            <text
              key={`t-${i}`}
              x={p.labelX}
              y={p.labelY}
              fontSize="10"
              fill="var(--muted-foreground)"
              textAnchor={p.labelAnchor}
              dominantBaseline="middle"
            >
              {p.name}
            </text>
          ))}
        </svg>
      </div>
    </div>
  );
}

function useCollapsed(key: string, defaultCollapsed = false): [boolean, () => void] {
  const storageKey = `mm-profile-collapsed:${key}`;
  const [collapsed, setCollapsed] = useState<boolean>(defaultCollapsed);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(storageKey);
    if (saved !== null) setCollapsed(saved === "1");
  }, [storageKey]);
  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(storageKey, next ? "1" : "0");
      }
      return next;
    });
  };
  return [collapsed, toggle];
}

function CollapsibleSection({
  storageKey,
  defaultCollapsed = false,
  icon,
  title,
  badge,
  children,
  outerStyle,
}: {
  storageKey: string;
  defaultCollapsed?: boolean;
  icon: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
  outerStyle?: React.CSSProperties;
}) {
  const [collapsed, toggle] = useCollapsed(storageKey, defaultCollapsed);
  const sectionId = `section-${storageKey}`;

  return (
    <section
      className="rounded-xl"
      style={{
        backgroundColor: "var(--card)",
        borderWidth: 1,
        borderColor: "var(--border)",
        ...outerStyle,
      }}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={!collapsed}
        aria-controls={sectionId}
        className="w-full flex items-center gap-2 px-6 py-4 text-left"
      >
        <span style={{ color: "var(--muted-foreground)" }}>{icon}</span>
        <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
          {title}
        </h3>
        {badge}
        <ChevronDown
          className="h-4 w-4 ml-auto transition-transform"
          style={{
            color: "var(--muted-foreground)",
            transform: collapsed ? "rotate(-90deg)" : "rotate(0deg)",
          }}
        />
      </button>
      {!collapsed && (
        <div id={sectionId} className="px-6 pb-6 flex flex-col gap-5">
          {children}
        </div>
      )}
    </section>
  );
}

function StatTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div
      className="rounded-lg px-3 py-3 flex flex-col gap-1"
      style={{ backgroundColor: "var(--secondary)" }}
    >
      <div className="flex items-center gap-1.5" style={{ color: "var(--muted-foreground)" }}>
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="text-sm font-semibold truncate" style={{ color: "var(--foreground)" }}>
        {value}
      </div>
    </div>
  );
}

function ChangePasswordCard() {
  const [formError, setFormError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) });

  const onSubmit = async (data: PasswordForm) => {
    setFormError(null);
    setSuccessMsg(null);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resp = await (api as any).POST("/v1/auth/change-password", {
        body: {
          current_password: data.current_password,
          new_password: data.new_password,
        },
      });
      if (resp.error) {
        const msg =
          (resp.error as { error?: { message?: string } })?.error?.message ??
          "Couldn't update password.";
        setFormError(msg);
        return;
      }
      setSuccessMsg("Password updated.");
      reset();
    } catch {
      setFormError("Network error.");
    }
  };

  return (
    <CollapsibleSection
      storageKey="password"
      defaultCollapsed
      icon={<KeyRound className="h-4 w-4" />}
      title="Change password"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
        <Field label="Current password" error={errors.current_password?.message}>
          <input
            type="password"
            autoComplete="current-password"
            className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
            style={{ ...inputStyle(!!errors.current_password), color: "var(--foreground)" }}
            {...register("current_password")}
          />
        </Field>
        <Field label="New password" error={errors.new_password?.message}>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Min 8 chars, uppercase + digit"
            className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
            style={{ ...inputStyle(!!errors.new_password), color: "var(--foreground)" }}
            {...register("new_password")}
          />
        </Field>
        <Field label="Confirm new password" error={errors.confirm_new_password?.message}>
          <input
            type="password"
            autoComplete="new-password"
            className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
            style={{ ...inputStyle(!!errors.confirm_new_password), color: "var(--foreground)" }}
            {...register("confirm_new_password")}
          />
        </Field>

        {formError && (
          <div
            className="px-3 py-2 rounded-lg text-sm"
            style={{ backgroundColor: "oklch(0.22 0.06 25)", color: "oklch(0.8 0.15 25)" }}
          >
            {formError}
          </div>
        )}
        {successMsg && (
          <div
            className="px-3 py-2 rounded-lg text-sm"
            style={{ backgroundColor: "oklch(0.22 0.06 145)", color: "oklch(0.8 0.15 145)" }}
          >
            {successMsg}
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="self-start flex items-center gap-2 py-2 px-4 rounded-lg text-sm font-medium text-white transition-opacity disabled:opacity-60"
          style={{ backgroundColor: "var(--tab-collaborative)" }}
        >
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Update password
        </button>
      </form>
    </CollapsibleSection>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
        {label}
      </label>
      {children}
      {error && (
        <p className="text-xs" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

function DangerZone() {
  const router = useRouter();
  const [showConfirm, setShowConfirm] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const logout = () => {
    clearTokens();
    wipeLocalUserState();
    router.replace("/login");
  };

  const doDelete = async () => {
    if (!password) {
      setError("Enter your password to confirm.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resp = await (api as any).DELETE("/v1/auth/me", {
        body: { password },
      });
      if (resp.error) {
        setError("Password doesn't match. Account not deleted.");
        return;
      }
      // Nuke every trace of the deleted account from the browser so a fresh
      // registration in the same tab doesn't inherit stale ratings / flags /
      // cached recs. Without this, Zustand's `hydrateFromServer` would push
      // the old local ratings back into the new user's DB row.
      clearTokens();
      wipeLocalUserState();
      router.replace("/register");
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <CollapsibleSection
      storageKey="danger"
      defaultCollapsed
      icon={<AlertTriangle className="h-4 w-4" style={{ color: "var(--destructive)" }} />}
      title="Danger zone"
      outerStyle={{ borderColor: "oklch(0.35 0.08 25)" }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg p-3" style={{ backgroundColor: "var(--secondary)" }}>
        <div>
          <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
            Sign out
          </p>
          <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            Sign out of this device. You can sign back in anytime.
          </p>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
          style={{
            backgroundColor: "transparent",
            borderWidth: 1,
            borderColor: "var(--border)",
            color: "var(--foreground)",
          }}
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>

      <div className="flex flex-col gap-3 rounded-lg p-3" style={{ backgroundColor: "oklch(0.18 0.04 25)" }}>
        <div>
          <p className="text-sm font-medium" style={{ color: "var(--destructive)" }}>
            Delete account
          </p>
          <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            This permanently deletes your account and all your ratings. This cannot be undone.
          </p>
        </div>

        {!showConfirm ? (
          <button
            onClick={() => setShowConfirm(true)}
            className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white"
            style={{ backgroundColor: "var(--destructive)" }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete my account
          </button>
        ) : (
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
              Confirm with your password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{
                backgroundColor: "var(--secondary)",
                borderWidth: 1,
                borderColor: error ? "var(--destructive)" : "var(--border)",
                color: "var(--foreground)",
              }}
            />
            {error && (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={doDelete}
                disabled={busy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white disabled:opacity-60"
                style={{ backgroundColor: "var(--destructive)" }}
              >
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Confirm delete
              </button>
              <button
                onClick={() => {
                  setShowConfirm(false);
                  setPassword("");
                  setError(null);
                }}
                className="px-3 py-1.5 rounded-lg text-sm"
                style={{
                  backgroundColor: "transparent",
                  borderWidth: 1,
                  borderColor: "var(--border)",
                  color: "var(--foreground)",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
