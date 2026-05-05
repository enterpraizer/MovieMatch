"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { RefreshCw, Trash2, Sparkles, Star } from "lucide-react";
import Image from "next/image";
import { MovieGrid, type MovieCardMovie } from "@/components/features/movie-card";
import { StarRating } from "@/components/features/rating";
import { useRatingsStore } from "@/store/ratings-store";

interface RecommendResponse {
  items: MovieCardMovie[];
  model_version: string;
  latency_ms: number;
  cached: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "mm-collab-results";

export function CollaborativeTab() {
  const ratings = useRatingsStore((s) => s.ratings);
  const clearRatings = useRatingsStore((s) => s.clearRatings);
  const storeCount = useRatingsStore((s) => s.ratingCount());
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const ratingCount = mounted ? storeCount : 0;

  const [results, setResults] = useState<MovieCardMovie[]>([]);
  const [modelVersion, setModelVersion] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trendingMovies, setTrendingMovies] = useState<
    { id: number; title: string; year: number | null; poster_url: string | null; avg_rating: number | null }[]
  >([]);
  const [trendingLoading, setTrendingLoading] = useState(true);
  const autoFetched = useRef(false);

  useEffect(() => {
    // Fetch TWO pools in parallel:
    //   /trending  — top popular (user recognises → can actually rate)
    //   /onboarding — divisive (each rating carries more signal)
    // Blend: trending first, then divisive, de-duped by id. This way the
    // "Rate more" grid leads with familiar titles then goes deeper.
    type Pick = { id: number; title: string; year: number | null; poster_url: string | null; avg_rating: number | null };
    Promise.all([
      fetch(`${API_URL}/v1/movies/trending`).then((r) => r.json()).catch(() => []),
      fetch(`${API_URL}/v1/movies/onboarding?limit=40`).then((r) => r.json()).catch(() => []),
    ])
      .then(([trending, divisive]) => {
        const popArr: Pick[] = Array.isArray(trending) ? trending : [];
        const divArr: Pick[] = Array.isArray(divisive) ? divisive : [];
        const seen = new Set<number>();
        const merged: Pick[] = [];
        for (const m of popArr) {
          if (!seen.has(m.id)) { merged.push(m); seen.add(m.id); }
        }
        for (const m of divArr) {
          if (!seen.has(m.id)) { merged.push(m); seen.add(m.id); }
        }
        setTrendingMovies(merged);
      })
      .finally(() => setTrendingLoading(false));
  }, []);

  useEffect(() => {
    try {
      const cached = sessionStorage.getItem(STORAGE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached) as MovieCardMovie[];
        if (parsed.length > 0) {
          setResults(parsed);
          autoFetched.current = true;
        }
      }
    } catch { /* ignore */ }
  }, []);

  const fetchRecommendations = useCallback(async () => {
    const token = typeof window !== "undefined"
      ? localStorage.getItem("mm_access_token")
      : null;

    if (!token) {
      window.location.href = "/register";
      return;
    }

    setIsLoading(true);
    setError(null);

    // Read the current ratings directly from the store (not from the closure)
    // so that actions like "Start over" — which clear the store and then
    // immediately call this function — send the *post-clear* state, not the
    // stale value that was frozen into fetchRecommendations' closure.
    const latestRatings = useRatingsStore.getState().ratings;
    const ratingsList = Object.entries(latestRatings).map(([movieId, score]) => ({
      movie_id: Number(movieId),
      score,
    }));
    const body = JSON.stringify({
      ratings: ratingsList,
      limit: 20,
      exclude_seen: true,
    });

    const doFetch = async (t: string) =>
      fetch(`${API_URL}/v1/recommendations/collaborative`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${t}`,
        },
        body,
      });

    try {
      let resp = await doFetch(token);

      if (resp.status === 401) {
        const refreshToken = localStorage.getItem("mm_refresh_token");
        if (refreshToken) {
          const rr = await fetch(`${API_URL}/v1/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          if (rr.ok) {
            const tokens = await rr.json();
            localStorage.setItem("mm_access_token", tokens.access_token);
            localStorage.setItem("mm_refresh_token", tokens.refresh_token);
            resp = await doFetch(tokens.access_token);
          } else {
            localStorage.removeItem("mm_access_token");
            localStorage.removeItem("mm_refresh_token");
            window.location.href = "/login";
            return;
          }
        } else {
          window.location.href = "/login";
          return;
        }
      }

      if (!resp.ok) throw new Error(`API error: ${resp.status}`);

      const data: RecommendResponse = await resp.json();
      setResults(data.items);
      setModelVersion(data.model_version ?? "");
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data.items));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }, [ratings]);

  // Auto-fetch on mount (and when the rating count changes meaningfully).
  // Backend does popularity fallback for users with no ratings, so this tab
  // always has content — no more "Rate 10 movies first" gate.
  useEffect(() => {
    if (autoFetched.current) return;
    const token = typeof window !== "undefined" ? localStorage.getItem("mm_access_token") : null;
    if (!token) return;
    autoFetched.current = true;
    void fetchRecommendations();
  }, [fetchRecommendations]);

  const handleStartOver = async () => {
    // Block the auto-fetch effect from firing during the reset handshake.
    autoFetched.current = true;
    setResults([]);
    sessionStorage.removeItem(STORAGE_KEY);
    await clearRatings();
    await fetchRecommendations();
  };

  const ratedIds = new Set(Object.keys(ratings).map(Number));
  const unratedTrending = trendingMovies.filter((m) => !ratedIds.has(m.id));

  return (
    <div className="flex flex-col gap-4 tab-content-enter">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        {modelVersion === "popularity" ? (
          <h2 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
            Popular now
            <span
              className="text-sm font-normal ml-2"
              style={{ color: "var(--muted-foreground)" }}
            >
              rate a few movies to personalise this
            </span>
          </h2>
        ) : (
          <h2 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
            Recommended for you
            {ratingCount > 0 && (
              <span
                className="text-sm font-normal ml-2"
                style={{ color: "var(--muted-foreground)" }}
              >
                based on {ratingCount} ratings
              </span>
            )}
          </h2>
        )}
        <div className="flex items-center gap-2">
          <button
            onClick={fetchRecommendations}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
            style={{
              backgroundColor: "var(--secondary)",
              color: "var(--secondary-foreground)",
            }}
          >
            <RefreshCw className={`h-3 w-3 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={handleStartOver}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
            style={{ color: "var(--muted-foreground)" }}
          >
            <Trash2 className="h-3 w-3" />
            Start over
          </button>
        </div>
      </div>

      {error && (
        <div
          className="flex items-center justify-between p-3 rounded-lg text-sm"
          style={{
            backgroundColor: "oklch(0.25 0.05 25)",
            color: "oklch(0.8 0.15 25)",
          }}
        >
          <span>{error}</span>
          <button onClick={fetchRecommendations} className="underline text-xs ml-2">
            Retry
          </button>
        </div>
      )}

      {/* ===== Section 1: Recommendations ===== */}
      <section
        className="rounded-xl p-4"
        style={{
          backgroundColor: "var(--card)",
          borderWidth: 1,
          borderColor: "var(--border)",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="h-4 w-4" style={{ color: "var(--tab-collaborative)" }} />
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: "var(--tab-collaborative)" }}
          >
            Recommendations
          </span>
        </div>
        <MovieGrid
          movies={results}
          isLoading={isLoading}
          showScore
          emptyMessage="No recommendations yet. Try rating more movies!"
        />
      </section>

      {/* ===== Section 2: Rate more — always visible, visually distinct ===== */}
      <section
        className="rounded-xl p-4"
        style={{
          backgroundColor: "oklch(0.16 0.02 300 / 0.35)",
          borderWidth: 1,
          borderStyle: "dashed",
          borderColor: "var(--tab-collaborative)",
        }}
      >
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-2">
            <Star className="h-4 w-4" style={{ color: "var(--accent)" }} />
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: "var(--accent)" }}
            >
              Rate more movies to refine
            </span>
          </div>
          <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            Set stars on movies you&apos;ve seen — results update on refresh
          </p>
        </div>

        {trendingLoading ? (
          <p className="text-xs py-4 text-center" style={{ color: "var(--muted-foreground)" }}>
            Loading picks…
          </p>
        ) : unratedTrending.length === 0 ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--muted-foreground)" }}>
            You&apos;ve rated everything in the pool. Start over to reset.
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {unratedTrending.slice(0, 12).map((movie) => (
              <div
                key={movie.id}
                className="flex flex-col gap-1.5 rounded-lg p-2"
                style={{ backgroundColor: "var(--card)" }}
              >
                <div
                  className="relative aspect-[2/3] overflow-hidden rounded-md"
                  style={{ backgroundColor: "var(--muted)" }}
                >
                  {movie.poster_url ? (
                    <Image
                      src={movie.poster_url}
                      alt={movie.title}
                      fill
                      className="object-cover"
                      sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
                    />
                  ) : null}
                </div>
                <h4
                  className="text-[11px] font-medium leading-tight line-clamp-1"
                  style={{ color: "var(--foreground)" }}
                >
                  {movie.title}
                </h4>
                <StarRating movieId={movie.id} movieTitle={movie.title} compact />
              </div>
            ))}
          </div>
        )}

        {ratingCount > 0 && (
          <div className="flex justify-center mt-4">
            <button
              type="button"
              onClick={fetchRecommendations}
              disabled={isLoading}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
              style={{
                backgroundColor: "var(--tab-collaborative)",
                boxShadow: "var(--shadow-glow-purple)",
              }}
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
              Update recommendations ({ratingCount} ratings)
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
