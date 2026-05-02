"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, BookmarkCheck, ExternalLink, Play, Sparkles, Trash2 } from "lucide-react";
import { StarRating } from "@/components/features/rating";
import { useRatingsStore } from "@/store/ratings-store";
import { api, getToken } from "@/lib/api/client";

interface MovieActionsProps {
  movieId: number;
  title: string;
  year: number | null;
}

function buildSearchUrl(base: string, title: string, year: number | null): string {
  const q = year ? `${title} ${year}` : title;
  return `${base}${encodeURIComponent(q)}`;
}

export function MovieActions({ movieId, title, year }: MovieActionsProps) {
  const [mounted, setMounted] = useState(false);
  const rating = useRatingsStore((s) => s.ratings[movieId] ?? 0);
  const removeRating = useRatingsStore((s) => s.removeRating);
  const [inWatchlist, setInWatchlist] = useState<boolean | null>(null);
  const [wlBusy, setWlBusy] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    if (!getToken()) {
      setInWatchlist(false);
      return;
    }
    (async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resp = await (api as any).GET("/v1/watchlist/ids");
      const ids = (resp.data as number[] | undefined) ?? [];
      setInWatchlist(ids.includes(movieId));
    })();
  }, [mounted, movieId]);

  const toggleWatchlist = async () => {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    setWlBusy(true);
    try {
      if (inWatchlist) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await (api as any).DELETE(`/v1/watchlist/${movieId}`);
        setInWatchlist(false);
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await (api as any).POST(`/v1/watchlist/${movieId}`);
        setInWatchlist(true);
      }
    } finally {
      setWlBusy(false);
    }
  };

  const hdrezkaUrl = buildSearchUrl(
    "https://hdrezka.ag/search/?do=search&subaction=search&q=",
    title,
    year,
  );
  const kinogoUrl = buildSearchUrl(
    "https://kinogo.la/index.php?do=search&subaction=search&story=",
    title,
    year,
  );

  return (
    <div className="flex flex-col gap-4 mt-3">
      {/* Rating */}
      <div
        className="flex items-center flex-wrap gap-3 p-3 rounded-lg"
        style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
      >
        <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
          Your rating:
        </span>
        <StarRating movieId={movieId} movieTitle={title} />
        {mounted && rating > 0 && (
          <button
            type="button"
            onClick={() => removeRating(movieId)}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors"
            style={{ color: "var(--muted-foreground)" }}
          >
            <Trash2 className="h-3 w-3" />
            Remove
          </button>
        )}
        {mounted && (
          <button
            type="button"
            onClick={toggleWatchlist}
            disabled={wlBusy}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-60"
            style={{
              backgroundColor: inWatchlist ? "var(--tab-collaborative)" : "transparent",
              color: inWatchlist ? "white" : "var(--foreground)",
              borderWidth: 1,
              borderColor: inWatchlist ? "transparent" : "var(--border)",
            }}
          >
            {inWatchlist ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
            {inWatchlist ? "Saved" : "Save to watch"}
          </button>
        )}
      </div>

      {/* More like this */}
      <Link
        href={`/movies/${movieId}/similar`}
        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium self-start transition-transform hover:scale-105"
        style={{
          backgroundColor: "var(--secondary)",
          color: "var(--foreground)",
          borderWidth: 1,
          borderColor: "var(--border)",
        }}
      >
        <Sparkles className="h-4 w-4" style={{ color: "var(--tab-search)" }} />
        More like this
      </Link>

      {/* Watch links */}
      <div className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-wider" style={{ color: "var(--muted-foreground)" }}>
          Watch now
        </p>
        <div className="flex flex-wrap gap-2">
          <a
            href={hdrezkaUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-transform hover:scale-105"
            style={{
              backgroundColor: "var(--tab-collaborative)",
              color: "white",
            }}
          >
            <Play className="h-4 w-4 fill-white" />
            HDrezka
            <ExternalLink className="h-3 w-3 opacity-70" />
          </a>
          <a
            href={kinogoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-transform hover:scale-105"
            style={{
              backgroundColor: "var(--tab-search)",
              color: "white",
            }}
          >
            <Play className="h-4 w-4 fill-white" />
            Kinogo
            <ExternalLink className="h-3 w-3 opacity-70" />
          </a>
        </div>
        <p className="text-xs" style={{ color: "var(--subtle-foreground)" }}>
          External search — availability depends on the site.
        </p>
      </div>
    </div>
  );
}
