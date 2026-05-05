"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { Search, SlidersHorizontal, Loader2, X, Film, Star, Flame, Calendar, TrendingUp, ArrowRight } from "lucide-react";
import { MovieGrid, type MovieCardMovie } from "@/components/features/movie-card";
import { useDebounce } from "@/lib/hooks/use-debounce";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CURRENT_YEAR = new Date().getFullYear();

const sanitizeYearInput = (v: string): string => v.replace(/[^\d]/g, "").slice(0, 4);

const clampYear = (v: string): string => {
  if (v === "") return "";
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  if (n < 1900) return "1900";
  if (n > CURRENT_YEAR) return String(CURRENT_YEAR);
  return String(n);
};

const GENRES = [
  "Action", "Adventure", "Animation", "Children", "Comedy", "Crime",
  "Documentary", "Drama", "Fantasy", "Film-Noir", "Horror", "Musical",
  "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western",
];

const GENRE_SLUG: Record<string, string> = {
  Action: "action", Adventure: "adventure", Animation: "animation",
  Children: "children", Comedy: "comedy", Crime: "crime",
  Documentary: "documentary", Drama: "drama", Fantasy: "fantasy",
  "Film-Noir": "film-noir", Horror: "horror", Musical: "musical",
  Mystery: "mystery", Romance: "romance", "Sci-Fi": "sci-fi",
  Thriller: "thriller", War: "war", Western: "western",
};

type OrderBy = "popularity" | "rating" | "year";

export default function BrowsePage() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 350);

  const [selectedGenres, setSelectedGenres] = useState<Set<string>>(new Set());
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [minRating, setMinRating] = useState("");
  const [orderBy, setOrderBy] = useState<OrderBy>("popularity");
  const [showFilters, setShowFilters] = useState(false);

  const [movies, setMovies] = useState<MovieCardMovie[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const isSearchMode = debouncedQuery.trim().length >= 1;

  const abortRef = useRef<AbortController | null>(null);

  const buildBrowseUrl = useCallback(
    (cursor: number | null) => {
      const params = new URLSearchParams({ limit: "30", order_by: orderBy });
      if (cursor != null) params.set("cursor", String(cursor));
      if (yearFrom) params.set("year_from", yearFrom);
      if (yearTo) params.set("year_to", yearTo);
      if (minRating) params.set("min_rating", minRating);
      for (const g of selectedGenres) {
        const slug = GENRE_SLUG[g];
        if (slug) params.append("genres", slug);
      }
      return `${API_URL}/v1/movies?${params}`;
    },
    [orderBy, yearFrom, yearTo, minRating, selectedGenres],
  );

  const fetchMovies = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);
    setNextCursor(null);

    try {
      if (isSearchMode) {
        const url = `${API_URL}/v1/movies/search?q=${encodeURIComponent(debouncedQuery)}`;
        const resp = await fetch(url, { signal: ac.signal });
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        const data = await resp.json();
        setMovies(Array.isArray(data) ? data.map(toCard) : []);
      } else {
        const resp = await fetch(buildBrowseUrl(null), { signal: ac.signal });
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        const data = await resp.json();
        setMovies((data.items ?? []).map(toCard));
        setNextCursor(data.next_cursor ?? null);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(e instanceof Error ? e.message : "Something went wrong");
      }
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, isSearchMode, buildBrowseUrl]);

  const loadMore = useCallback(async () => {
    if (nextCursor == null || loadingMore) return;
    setLoadingMore(true);
    try {
      const resp = await fetch(buildBrowseUrl(nextCursor));
      if (!resp.ok) throw new Error(`API error: ${resp.status}`);
      const data = await resp.json();
      setMovies((prev) => [...prev, ...(data.items ?? []).map(toCard)]);
      setNextCursor(data.next_cursor ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  }, [nextCursor, loadingMore, buildBrowseUrl]);

  useEffect(() => {
    fetchMovies();
  }, [fetchMovies]);

  const toggleGenre = (g: string) => {
    const next = new Set(selectedGenres);
    if (next.has(g)) next.delete(g);
    else next.add(g);
    setSelectedGenres(next);
  };

  const clearFilters = () => {
    setSelectedGenres(new Set());
    setYearFrom("");
    setYearTo("");
    setMinRating("");
    setOrderBy("popularity");
  };

  const hasActiveFilters =
    selectedGenres.size > 0 || yearFrom !== "" || yearTo !== "" || minRating !== "";

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "var(--background)" }}>
      <header
        className="sticky top-0 z-40 backdrop-blur-lg"
        style={{
          backgroundColor: "oklch(0.13 0.005 260 / 0.9)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link href="/" className="flex items-center gap-1.5 text-sm font-semibold" style={{ color: "var(--foreground)" }}>
            <Film className="h-4 w-4" style={{ color: "var(--tab-collaborative)" }} />
            MovieMatch
          </Link>
          <span className="text-sm" style={{ color: "var(--muted-foreground)" }}>/ Browse</span>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full flex flex-col gap-4">
        {/* Search bar */}
        <div className="flex gap-2">
          <div
            className="flex items-center gap-2 flex-1 px-3 py-2.5 rounded-lg"
            style={{
              backgroundColor: "var(--secondary)",
              borderWidth: 1,
              borderColor: "var(--border)",
            }}
          >
            <Search className="h-4 w-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search movie by title..."
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--muted-foreground)]"
              style={{ color: "var(--foreground)" }}
            />
            {query && (
              <button onClick={() => setQuery("")} type="button">
                <X className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
              </button>
            )}
            {loading && (
              <Loader2
                className="h-4 w-4 animate-spin shrink-0"
                style={{ color: "var(--tab-collaborative)" }}
              />
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            aria-label="Toggle filters"
            className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium"
            style={{
              backgroundColor: showFilters || hasActiveFilters ? "var(--tab-collaborative)" : "var(--secondary)",
              color: showFilters || hasActiveFilters ? "white" : "var(--secondary-foreground)",
            }}
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Filters</span>
            {hasActiveFilters && (
              <span
                className="text-[10px] font-bold rounded-full px-1.5 py-0.5"
                style={{ backgroundColor: "oklch(0 0 0 / 0.2)" }}
              >
                {selectedGenres.size + (yearFrom ? 1 : 0) + (yearTo ? 1 : 0) + (minRating ? 1 : 0)}
              </span>
            )}
          </button>
        </div>

        {/* Filter panel — styled */}
        {showFilters && (
          <div
            className="relative flex flex-col gap-5 p-5 rounded-xl overflow-hidden"
            style={{
              backgroundColor: "var(--card)",
              borderWidth: 1,
              borderColor: "var(--border)",
              boxShadow: "0 4px 24px oklch(0 0 0 / 0.25)",
            }}
          >
            {/* left accent bar */}
            <div
              className="absolute left-0 top-0 bottom-0 w-1"
              style={{
                background:
                  "linear-gradient(to bottom, var(--tab-collaborative), var(--tab-search))",
              }}
            />

            {/* Header row */}
            <div className="flex items-center justify-between pl-2">
              <div className="flex items-center gap-2">
                <SlidersHorizontal
                  className="h-4 w-4"
                  style={{ color: "var(--tab-collaborative)" }}
                />
                <h3
                  className="text-sm font-semibold"
                  style={{ color: "var(--foreground)" }}
                >
                  Refine catalog
                </h3>
              </div>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors"
                  style={{
                    backgroundColor: "transparent",
                    color: "var(--muted-foreground)",
                    borderWidth: 1,
                    borderColor: "var(--border)",
                  }}
                >
                  <X className="h-3 w-3" />
                  Clear all
                </button>
              )}
            </div>

            {/* Genres */}
            <div className="flex flex-col gap-2 pl-2">
              <div className="flex items-center gap-1.5">
                <Film className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />
                <label
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  Genres
                </label>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {GENRES.map((g) => {
                  const active = selectedGenres.has(g);
                  return (
                    <button
                      type="button"
                      key={g}
                      onClick={() => toggleGenre(g)}
                      className="px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150"
                      style={{
                        backgroundColor: active ? "var(--tab-collaborative)" : "var(--secondary)",
                        color: active ? "white" : "var(--secondary-foreground)",
                        borderWidth: 1,
                        borderColor: active ? "var(--tab-collaborative)" : "transparent",
                        boxShadow: active ? "0 0 0 3px oklch(0.58 0.22 300 / 0.18)" : "none",
                      }}
                    >
                      {active ? "✓ " : ""}
                      {g}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 3-col row: Year / Rating / Sort */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 pl-2">
              {/* Year range */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <Calendar className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />
                  <label
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    Year
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder="From"
                    min={1900}
                    max={CURRENT_YEAR}
                    value={yearFrom}
                    onChange={(e) => setYearFrom(sanitizeYearInput(e.target.value))}
                    onBlur={(e) => setYearFrom(clampYear(e.target.value))}
                    className="flex-1 min-w-0 px-3 py-1.5 rounded-lg text-sm outline-none transition-colors"
                    style={{
                      backgroundColor: "var(--secondary)",
                      borderWidth: 1,
                      borderColor: yearFrom ? "var(--tab-collaborative)" : "var(--border)",
                      color: "var(--foreground)",
                    }}
                  />
                  <ArrowRight className="h-3 w-3 shrink-0" style={{ color: "var(--muted-foreground)" }} />
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder="To"
                    min={1900}
                    max={CURRENT_YEAR}
                    value={yearTo}
                    onChange={(e) => setYearTo(sanitizeYearInput(e.target.value))}
                    onBlur={(e) => setYearTo(clampYear(e.target.value))}
                    className="flex-1 min-w-0 px-3 py-1.5 rounded-lg text-sm outline-none transition-colors"
                    style={{
                      backgroundColor: "var(--secondary)",
                      borderWidth: 1,
                      borderColor: yearTo ? "var(--tab-collaborative)" : "var(--border)",
                      color: "var(--foreground)",
                    }}
                  />
                </div>
              </div>

              {/* Min rating — clickable stars */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <Star
                    className="h-3 w-3"
                    style={{ fill: "var(--accent)", color: "var(--accent)" }}
                  />
                  <label
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    Min rating {minRating && <span style={{ color: "var(--foreground)" }}>· {minRating}+</span>}
                  </label>
                </div>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((n) => {
                    const filled = minRating !== "" && Number(minRating) >= n;
                    const half = minRating !== "" && Number(minRating) >= n - 0.5 && !filled;
                    const nextVal = minRating === String(n) ? String(n - 0.5) : String(n);
                    return (
                      <button
                        key={n}
                        type="button"
                        onClick={() =>
                          setMinRating(minRating === nextVal ? "" : nextVal)
                        }
                        aria-label={`Set minimum rating to ${n}`}
                        className="relative p-1 transition-transform hover:scale-110"
                      >
                        <Star
                          className="h-5 w-5"
                          style={{
                            fill: filled || half ? "var(--accent)" : "transparent",
                            color: filled || half ? "var(--accent)" : "var(--muted-foreground)",
                            opacity: half ? 0.6 : 1,
                          }}
                        />
                      </button>
                    );
                  })}
                  {minRating && (
                    <button
                      type="button"
                      onClick={() => setMinRating("")}
                      className="ml-1 text-[11px] underline"
                      style={{ color: "var(--muted-foreground)" }}
                    >
                      clear
                    </button>
                  )}
                </div>
              </div>

              {/* Sort by — pill group */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1.5">
                  <TrendingUp className="h-3 w-3" style={{ color: "var(--muted-foreground)" }} />
                  <label
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    Sort by
                  </label>
                </div>
                <div
                  className="inline-flex rounded-lg p-0.5"
                  style={{
                    backgroundColor: "var(--secondary)",
                    borderWidth: 1,
                    borderColor: "var(--border)",
                  }}
                >
                  {(
                    [
                      { k: "popularity", label: "Popular", icon: Flame },
                      { k: "rating", label: "Rating", icon: Star },
                      { k: "year", label: "Year", icon: Calendar },
                    ] as { k: OrderBy; label: string; icon: typeof Flame }[]
                  ).map(({ k, label, icon: Icon }) => {
                    const active = orderBy === k;
                    return (
                      <button
                        key={k}
                        type="button"
                        onClick={() => setOrderBy(k)}
                        className="flex items-center gap-1 px-3 py-1 rounded-md text-xs font-medium transition-colors"
                        style={{
                          backgroundColor: active ? "var(--tab-collaborative)" : "transparent",
                          color: active ? "white" : "var(--muted-foreground)",
                        }}
                      >
                        <Icon className="h-3 w-3" />
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <p
              className="text-[11px] pl-2"
              style={{ color: "var(--subtle-foreground)" }}
            >
              Filters apply when the search box is empty.
            </p>
          </div>
        )}

        {error && (
          <div
            className="p-3 rounded-lg text-sm text-center"
            style={{ backgroundColor: "oklch(0.25 0.05 25)", color: "oklch(0.8 0.15 25)" }}
          >
            {error}
          </div>
        )}

        <MovieGrid
          movies={movies}
          isLoading={loading && movies.length === 0}
          emptyMessage={
            query
              ? `No movies found for "${query}"`
              : "No movies match these filters"
          }
        />

        {!isSearchMode && nextCursor != null && (
          <div className="flex justify-center py-4">
            <button
              type="button"
              onClick={loadMore}
              disabled={loadingMore}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-opacity disabled:opacity-60"
              style={{
                backgroundColor: "var(--tab-collaborative)",
                color: "white",
              }}
            >
              {loadingMore ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading...
                </>
              ) : (
                <>Load more movies</>
              )}
            </button>
          </div>
        )}

        {!isSearchMode && nextCursor == null && movies.length > 0 && !loading && (
          <p className="text-center text-xs py-4" style={{ color: "var(--subtle-foreground)" }}>
            You've reached the end ({movies.length} movies)
          </p>
        )}
      </main>
    </div>
  );
}

function toCard(m: {
  id: number;
  title: string;
  year: number | null;
  avg_rating: number | null;
  rating_count?: number;
  genres?: string[];
  poster_url: string | null;
}): MovieCardMovie {
  return {
    movie_id: m.id,
    title: m.title,
    year: m.year,
    avg_rating: m.avg_rating,
    genres: m.genres ?? [],
    poster_url: m.poster_url,
  };
}
