"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Search, X, SlidersHorizontal, Loader2, Plus } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { MovieGrid, type MovieCardMovie } from "@/components/features/movie-card";
import { useDebounce } from "@/lib/hooks/use-debounce";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXAMPLE_QUERIES = [
  "dark comedy crime",
  "romantic time travel",
  "space exploration epic",
  "psychological thriller twist",
  "coming of age summer",
  "heist with clever plan",
  "dystopian future society",
  "inspiring underdog story",
];

interface SearchResult {
  movie_id: number;
  title: string;
  year: number | null;
  avg_rating: number | null;
  poster_url: string | null;
  genres: string[];
  rrf_score: number;
}

const PAGE_SIZE = 20;
const MAX_OFFSET = 200;
const STATE_KEY = "mm-search-state";

interface PersistedState {
  query: string;
  results: MovieCardMovie[];
  yearFrom: string;
  yearTo: string;
  minRating: string;
  offset: number;
  hasMore: boolean;
}

function loadState(): PersistedState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STATE_KEY);
    return raw ? (JSON.parse(raw) as PersistedState) : null;
  } catch {
    return null;
  }
}

export function SearchTab() {
  // Hydrate from sessionStorage so that navigating to a movie and back doesn't
  // wipe the search query + results + pagination.
  const saved = typeof window !== "undefined" ? loadState() : null;
  const [query, setQuery] = useState(saved?.query ?? "");
  const debouncedQuery = useDebounce(query, 350);
  const [results, setResults] = useState<MovieCardMovie[]>(saved?.results ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [yearFrom, setYearFrom] = useState(saved?.yearFrom ?? "");
  const [yearTo, setYearTo] = useState(saved?.yearTo ?? "");
  const [minRating, setMinRating] = useState(saved?.minRating ?? "");
  const [hasPreviousData, setHasPreviousData] = useState((saved?.results?.length ?? 0) > 0);
  const [hasMore, setHasMore] = useState(saved?.hasMore ?? false);
  const [offset, setOffset] = useState(saved?.offset ?? 0);
  const inputRef = useRef<HTMLInputElement>(null);
  const hydrated = useRef(saved !== null);

  // Persist state on every change — cheap JSON serialize.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const snapshot: PersistedState = { query, results, yearFrom, yearTo, minRating, offset, hasMore };
    try {
      sessionStorage.setItem(STATE_KEY, JSON.stringify(snapshot));
    } catch {
      /* quota — ignore */
    }
  }, [query, results, yearFrom, yearTo, minRating, offset, hasMore]);

  const runSearch = useCallback(
    async (append: boolean, explicitOffset: number) => {
      if (append) setLoadingMore(true);
      else setIsLoading(true);
      setError(null);

      try {
        const resp = await fetch(`${API_URL}/v1/recommendations/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: debouncedQuery,
            limit: PAGE_SIZE,
            offset: explicitOffset,
            filters: {
              year_from: yearFrom ? Number(yearFrom) : null,
              year_to: yearTo ? Number(yearTo) : null,
              min_rating: minRating ? Number(minRating) : null,
            },
          }),
        });
        if (!resp.ok) throw new Error(`Search failed: ${resp.status}`);
        const data = await resp.json();
        const items: MovieCardMovie[] = (data.items ?? []).map(
          (m: SearchResult & { score?: number; reason?: string }) => ({
            movie_id: m.movie_id,
            title: m.title,
            year: m.year,
            genres: m.genres ?? [],
            avg_rating: m.avg_rating,
            poster_url: m.poster_url,
            score: m.score ?? m.rrf_score,
            reason: m.reason ?? "semantic match",
          }),
        );
        setResults((prev) => (append ? [...prev, ...items] : items));
        setHasPreviousData((append ? results.length : items.length) > 0);
        // Page is full + room left below MAX_OFFSET ⇒ assume more exists.
        setHasMore(
          items.length === PAGE_SIZE && explicitOffset + PAGE_SIZE < MAX_OFFSET,
        );
        setOffset(explicitOffset + items.length);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        if (append) setLoadingMore(false);
        else setIsLoading(false);
      }
    },
    // results.length read is a harmless stale closure (used only for UX flag);
    // including it would re-create runSearch on every append.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [debouncedQuery, yearFrom, yearTo, minRating],
  );

  useEffect(() => {
    if (debouncedQuery.length < 2) {
      if (debouncedQuery.length === 0) {
        setResults([]);
        setHasMore(false);
        setOffset(0);
      }
      return;
    }
    // On first mount after a session restore, skip the re-fetch — cached
    // results already match the query. Clearing the flag unconditionally
    // means any subsequent query/filter change goes through runSearch.
    // DO NOT add `results.length` to deps: appending via Load more would
    // re-trigger this effect and overwrite the appended page.
    if (hydrated.current) {
      hydrated.current = false;
      return;
    }
    void runSearch(false, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, yearFrom, yearTo, minRating]);

  const handleChipClick = (q: string) => {
    setQuery(q);
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col gap-4 tab-content-enter">
      {/* Search input */}
      <div className="flex gap-2">
        <div
          className="flex items-center gap-2 flex-1 px-3 py-2.5 rounded-lg transition-colors"
          style={{
            backgroundColor: "var(--secondary)",
            borderWidth: 1,
            borderColor: "var(--border)",
          }}
        >
          <Search className="h-4 w-4 shrink-0" style={{ color: "var(--muted-foreground)" }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe a movie you'd like to watch..."
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--muted-foreground)]"
            style={{ color: "var(--foreground)" }}
          />
          {query && (
            <button onClick={() => setQuery("")} className="shrink-0">
              <X className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
            </button>
          )}
          {isLoading && <Loader2 className="h-4 w-4 animate-spin shrink-0" style={{ color: "var(--tab-search)" }} />}
        </div>
        <button
          onClick={() => setShowFilters((v) => !v)}
          aria-label="Toggle filters"
          className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
          style={{
            backgroundColor: showFilters ? "var(--tab-search)" : "var(--secondary)",
            color: showFilters ? "white" : "var(--secondary-foreground)",
          }}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Filters</span>
        </button>
      </div>

      {/* Filters panel */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div
              className="flex flex-wrap gap-3 p-3 rounded-lg"
              style={{ backgroundColor: "var(--card)" }}
            >
              <div className="flex items-center gap-2">
                <label className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  Year
                </label>
                <input
                  type="number"
                  value={yearFrom}
                  onChange={(e) => setYearFrom(e.target.value)}
                  placeholder="From"
                  className="w-20 px-2 py-1 rounded text-xs bg-transparent outline-none"
                  style={{ borderWidth: 1, borderColor: "var(--border)", color: "var(--foreground)" }}
                />
                <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>—</span>
                <input
                  type="number"
                  value={yearTo}
                  onChange={(e) => setYearTo(e.target.value)}
                  placeholder="To"
                  className="w-20 px-2 py-1 rounded text-xs bg-transparent outline-none"
                  style={{ borderWidth: 1, borderColor: "var(--border)", color: "var(--foreground)" }}
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  Min rating
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="5"
                  value={minRating}
                  onChange={(e) => setMinRating(e.target.value)}
                  placeholder="3.5"
                  className="w-16 px-2 py-1 rounded text-xs bg-transparent outline-none"
                  style={{ borderWidth: 1, borderColor: "var(--border)", color: "var(--foreground)" }}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Content */}
      {query.length === 0 && (
        <div className="flex flex-col items-center gap-6 py-8">
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            What are you in the mood for?
          </p>
          <div className="flex flex-wrap justify-center gap-2 max-w-lg">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => handleChipClick(q)}
                className="px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
                style={{
                  backgroundColor: "var(--secondary)",
                  color: "var(--secondary-foreground)",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {query.length > 0 && query.length < 2 && (
        <p className="text-center text-sm py-8" style={{ color: "var(--muted-foreground)" }}>
          Keep typing...
        </p>
      )}

      {query.length >= 2 && error && (
        <div
          className="p-4 rounded-lg text-sm text-center"
          style={{ backgroundColor: "var(--card)", color: "oklch(0.8 0.15 25)" }}
        >
          {error}
        </div>
      )}

      {query.length >= 2 && !error && (
        <div
          className="transition-opacity duration-200 flex flex-col gap-4"
          style={{ opacity: isLoading && hasPreviousData ? 0.6 : 1 }}
        >
          <MovieGrid
            movies={results}
            isLoading={isLoading && !hasPreviousData}
            emptyMessage={`No movies found for "${debouncedQuery}"`}
          />

          {hasMore && !isLoading && results.length > 0 && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={() => runSearch(true, offset)}
                disabled={loadingMore}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-60"
                style={{
                  backgroundColor: "var(--secondary)",
                  color: "var(--secondary-foreground)",
                  borderWidth: 1,
                  borderColor: "var(--border)",
                }}
              >
                {loadingMore ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Plus className="h-3.5 w-3.5" />
                )}
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}

          {!hasMore && !isLoading && results.length >= PAGE_SIZE && (
            <p
              className="text-center text-xs pt-2"
              style={{ color: "var(--muted-foreground)" }}
            >
              End of results — refine the query to find more.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
