"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence, type PanInfo } from "framer-motion";
import { Film, ArrowRight, ThumbsUp, ThumbsDown, LayoutGrid, Layers } from "lucide-react";
import Image from "next/image";
import { useRatingsStore } from "@/store/ratings-store";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { StarRating } from "./StarRating";

interface TrendingMovie {
  id: number;
  title: string;
  year: number | null;
  poster_url: string | null;
  avg_rating: number | null;
}

interface RatingOnboardingProps {
  movies: TrendingMovie[];
  isLoading: boolean;
  onReady: () => void;
  requiredCount?: number;
}

type Mode = "swipe" | "grid";

export function RatingOnboarding({
  movies,
  isLoading,
  onReady,
  requiredCount = 10,
}: RatingOnboardingProps) {
  const storeRatingCount = useRatingsStore((s) => s.ratingCount());
  const setRating = useRatingsStore((s) => s.setRating);
  const userRatings = useRatingsStore((s) => s.ratings);
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<Mode>("swipe");
  const [swipeIndex, setSwipeIndex] = useState(0);
  useEffect(() => {
    setMounted(true);
  }, []);
  const ratingCount = mounted ? storeRatingCount : 0;
  const progress = Math.min(100, (ratingCount / requiredCount) * 100);
  const isReady = mounted && ratingCount >= requiredCount;

  const queue = useMemo(
    () => movies.filter((m) => !(m.id in userRatings)),
    [movies, userRatings],
  );
  const current = queue[swipeIndex];
  const upcoming = queue[swipeIndex + 1];

  const vote = (liked: boolean) => {
    if (!current) return;
    setRating(current.id, liked ? 4.5 : 2.5);
    setSwipeIndex((i) => i + 1);
  };

  const onDragEnd = (_: unknown, info: PanInfo) => {
    const threshold = 100;
    if (info.offset.x > threshold) vote(true);
    else if (info.offset.x < -threshold) vote(false);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Progress header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
              {isReady
                ? "You're all set! Ready for recommendations."
                : `Rate at least ${requiredCount} movies to unlock recommendations`}
            </p>
            <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
              Only rate movies you&apos;ve actually seen — skip the rest
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs tabular-nums" style={{ color: "var(--muted-foreground)" }}>
              {ratingCount}/{requiredCount}
            </span>
            <div
              className="flex rounded-lg overflow-hidden"
              style={{ borderWidth: 1, borderColor: "var(--border)" }}
            >
              <button
                type="button"
                onClick={() => setMode("swipe")}
                aria-pressed={mode === "swipe"}
                className="p-1.5 transition-colors"
                style={{
                  backgroundColor: mode === "swipe" ? "var(--tab-collaborative)" : "transparent",
                  color: mode === "swipe" ? "white" : "var(--muted-foreground)",
                }}
                title="Swipe mode"
              >
                <Layers className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setMode("grid")}
                aria-pressed={mode === "grid"}
                className="p-1.5 transition-colors"
                style={{
                  backgroundColor: mode === "grid" ? "var(--tab-collaborative)" : "transparent",
                  color: mode === "grid" ? "white" : "var(--muted-foreground)",
                }}
                title="Grid mode"
              >
                <LayoutGrid className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
        <Progress value={progress} />
      </div>

      {/* SWIPE MODE */}
      {mode === "swipe" && (
        <>
          {isLoading ? (
            <div className="mx-auto w-full max-w-sm">
              <Skeleton className="aspect-[2/3] w-full rounded-xl" />
            </div>
          ) : !current ? (
            <div
              className="mx-auto w-full max-w-sm rounded-xl p-6 text-center"
              style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
            >
              <p className="text-sm" style={{ color: "var(--foreground)" }}>
                No more cards — switch to grid to review or fine-tune your ratings.
              </p>
            </div>
          ) : (
            <div className="relative mx-auto w-full max-w-sm h-[480px] sm:h-[560px]">
              {upcoming && (
                <div
                  className="absolute inset-0 rounded-xl overflow-hidden opacity-50 scale-95"
                  style={{ backgroundColor: "var(--card)" }}
                  aria-hidden
                >
                  <MoviePoster movie={upcoming} />
                </div>
              )}
              <AnimatePresence mode="wait">
                <motion.div
                  key={current.id}
                  drag="x"
                  dragConstraints={{ left: 0, right: 0 }}
                  dragElastic={0.7}
                  onDragEnd={onDragEnd}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, x: 0 }}
                  whileDrag={{ cursor: "grabbing" }}
                  className="absolute inset-0 rounded-xl overflow-hidden cursor-grab"
                  style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
                >
                  <MoviePoster movie={current} showTitle />
                </motion.div>
              </AnimatePresence>

              <div className="absolute -bottom-16 left-0 right-0 flex items-center justify-center gap-4">
                <button
                  type="button"
                  onClick={() => vote(false)}
                  className="h-12 w-12 rounded-full flex items-center justify-center transition-transform active:scale-90"
                  style={{
                    backgroundColor: "oklch(0.3 0.08 25)",
                    color: "oklch(0.85 0.15 25)",
                    borderWidth: 1,
                    borderColor: "oklch(0.4 0.1 25)",
                  }}
                  aria-label="Dislike"
                >
                  <ThumbsDown className="h-5 w-5" />
                </button>
                <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  Swipe or tap
                </p>
                <button
                  type="button"
                  onClick={() => vote(true)}
                  className="h-12 w-12 rounded-full flex items-center justify-center transition-transform active:scale-90"
                  style={{
                    backgroundColor: "var(--tab-collaborative)",
                    color: "white",
                  }}
                  aria-label="Like"
                >
                  <ThumbsUp className="h-5 w-5" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* GRID MODE */}
      {mode === "grid" && (
        <>
          {isLoading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-2">
                  <Skeleton className="aspect-[2/3] w-full rounded-lg" />
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
              {movies.slice(0, 40).map((movie) => (
                <div
                  key={movie.id}
                  className="flex flex-col gap-2 rounded-lg p-2 transition-colors"
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
                        sizes="(max-width: 640px) 50vw, 25vw"
                      />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <Film className="h-8 w-8" style={{ color: "var(--muted-foreground)", opacity: 0.4 }} />
                      </div>
                    )}
                  </div>
                  <h4
                    className="text-xs font-medium leading-tight line-clamp-1"
                    style={{ color: "var(--foreground)" }}
                  >
                    {movie.title}
                    {movie.year && (
                      <span style={{ color: "var(--muted-foreground)" }}> ({movie.year})</span>
                    )}
                  </h4>
                  <StarRating movieId={movie.id} movieTitle={movie.title} compact />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* CTA Button */}
      {isReady && (
        <div className={`flex justify-center ${mode === "swipe" ? "mt-20" : ""}`} style={{ animation: "tab-enter 0.3s ease-out" }}>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onReady();
            }}
            className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-semibold text-white transition-shadow duration-200 cursor-pointer"
            style={{
              backgroundColor: "var(--tab-collaborative)",
              boxShadow: "var(--shadow-glow-purple)",
              pointerEvents: "auto",
              position: "relative",
              zIndex: 50,
            }}
          >
            Get My Recommendations
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

function MoviePoster({ movie, showTitle }: { movie: TrendingMovie; showTitle?: boolean }) {
  return (
    <div className="relative w-full h-full">
      {movie.poster_url ? (
        <Image
          src={movie.poster_url}
          alt={movie.title}
          fill
          className="object-cover"
          sizes="420px"
          priority
        />
      ) : (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ backgroundColor: "var(--muted)" }}
        >
          <Film className="h-16 w-16" style={{ color: "var(--muted-foreground)", opacity: 0.4 }} />
        </div>
      )}
      {showTitle && (
        <div
          className="absolute bottom-0 left-0 right-0 p-4 flex flex-col gap-1"
          style={{
            background:
              "linear-gradient(to top, oklch(0 0 0 / 0.85), oklch(0 0 0 / 0.1))",
          }}
        >
          <h4 className="text-base font-semibold text-white line-clamp-2">{movie.title}</h4>
          <p className="text-xs text-white/80">
            {movie.year ?? ""}
            {movie.avg_rating != null && ` · ★ ${movie.avg_rating.toFixed(1)}`}
          </p>
        </div>
      )}
    </div>
  );
}
