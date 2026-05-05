"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Sparkles } from "lucide-react";
import { MovieGrid, type MovieCardMovie } from "@/components/features/movie-card";
import { BackButton } from "@/components/common/BackButton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SimilarResult {
  id: number;
  title: string;
  year: number | null;
  avg_rating: number | null;
  poster_url: string | null;
  genres: string[];
}

export default function SimilarPage() {
  const params = useParams();
  const id = Array.isArray(params?.id) ? params.id[0] : (params?.id as string);
  const [items, setItems] = useState<MovieCardMovie[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceTitle, setSourceTitle] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [detail, sim] = await Promise.all([
          fetch(`${API_URL}/v1/movies/${id}`).then((r) => (r.ok ? r.json() : null)),
          fetch(`${API_URL}/v1/movies/${id}/similar?limit=24`).then((r) =>
            r.ok ? r.json() : [],
          ),
        ]);
        if (cancelled) return;
        setSourceTitle(detail?.title ?? null);
        setItems(
          (sim as SimilarResult[]).map((m) => ({
            movie_id: m.id,
            title: m.title,
            year: m.year,
            genres: m.genres ?? [],
            avg_rating: m.avg_rating,
            poster_url: m.poster_url,
            reason: "Semantic match",
          })),
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      <header
        className="sticky top-0 z-10 backdrop-blur-lg"
        style={{
          backgroundColor: "oklch(0.13 0.005 260 / 0.9)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
          <BackButton
            fallbackHref={`/movies/${id}`}
            className="flex items-center gap-1 text-sm px-2 py-1 rounded-lg cursor-pointer"
            style={{ color: "var(--muted-foreground)" }}
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </BackButton>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" style={{ color: "var(--tab-search)" }} />
            <h1 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
              More like {sourceTitle ? `"${sourceTitle}"` : "this"}
            </h1>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <MovieGrid
          movies={items}
          isLoading={loading}
          emptyMessage="No similar movies found."
        />
      </main>
    </div>
  );
}
