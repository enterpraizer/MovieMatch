"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { motion, AnimatePresence, type PanInfo } from "framer-motion";
import { ArrowRight, Film, Loader2, SkipForward, ThumbsDown, ThumbsUp } from "lucide-react";
import { useRatingsStore } from "@/store/ratings-store";
import { Progress } from "@/components/ui/progress";
import { getToken } from "@/lib/api/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DONE_KEY = "mm-onboarding-done";
const TARGET = 10;

interface TrendingMovie {
  id: number;
  title: string;
  year: number | null;
  poster_url: string | null;
  avg_rating: number | null;
}

export default function OnboardingPage() {
  const router = useRouter();
  const setRating = useRatingsStore((s) => s.setRating);
  const ratingCount = useRatingsStore((s) => s.ratingCount());
  const localRatings = useRatingsStore((s) => s.ratings);

  const [movies, setMovies] = useState<TrendingMovie[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [index, setIndex] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Guard: already done → go home. Also require authentication.
    if (typeof window === "undefined") return;
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    if (window.localStorage.getItem(DONE_KEY) === "1") {
      router.replace("/");
      return;
    }
  }, [router]);

  useEffect(() => {
    fetch(`${API_URL}/v1/movies/onboarding?limit=40`)
      .then((r) => r.json())
      .then((data) => setMovies(Array.isArray(data) ? data : []))
      .catch(() => setMovies([]))
      .finally(() => setIsLoading(false));
  }, []);

  const queue = useMemo(
    () => movies.filter((m) => !(m.id in localRatings)),
    [movies, localRatings],
  );
  const current = queue[index];
  const upcoming = queue[index + 1];

  const vote = (liked: boolean) => {
    if (!current) return;
    setRating(current.id, liked ? 4.5 : 2.5);
    setIndex((i) => i + 1);
  };

  const skip = () => setIndex((i) => i + 1);

  const onDragEnd = (_: unknown, info: PanInfo) => {
    const threshold = 100;
    if (info.offset.x > threshold) vote(true);
    else if (info.offset.x < -threshold) vote(false);
  };

  const finish = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(DONE_KEY, "1");
    }
    setFinishing(true);
    router.replace("/");
  };

  const progress = Math.min(100, (ratingCount / TARGET) * 100);
  const canFinish = mounted && ratingCount >= TARGET;
  const ranOut = !isLoading && !current;

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-8"
      style={{ backgroundColor: "var(--background)" }}
    >
      <div className="w-full max-w-md flex flex-col gap-6">
        <div className="flex flex-col gap-2 text-center">
          <h1 className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
            Welcome — let&apos;s calibrate your taste
          </h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            Swipe right if you liked the movie, left if not. We need at least {TARGET} to start.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Progress value={progress} />
          <span className="text-xs tabular-nums shrink-0" style={{ color: "var(--muted-foreground)" }}>
            {mounted ? ratingCount : 0}/{TARGET}
          </span>
        </div>

        {isLoading ? (
          <div
            className="h-[420px] sm:h-[480px] rounded-xl flex items-center justify-center"
            style={{ backgroundColor: "var(--card)" }}
          >
            <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--muted-foreground)" }} />
          </div>
        ) : ranOut ? (
          <div
            className="h-[420px] sm:h-[480px] rounded-xl flex items-center justify-center text-center p-6"
            style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
          >
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              No more movies to swipe. Hit &quot;Done&quot; below to continue.
            </p>
          </div>
        ) : (
          <div className="relative h-[420px] sm:h-[480px]">
            {upcoming && (
              <div
                className="absolute inset-0 rounded-xl overflow-hidden opacity-50 scale-95"
                style={{ backgroundColor: "var(--card)" }}
                aria-hidden
              >
                <Poster movie={upcoming} />
              </div>
            )}
            <AnimatePresence mode="wait">
              <motion.div
                key={current!.id}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.7}
                onDragEnd={onDragEnd}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, x: 0 }}
                whileDrag={{ cursor: "grabbing" }}
                className="absolute inset-0 rounded-xl overflow-hidden cursor-grab"
                style={{
                  backgroundColor: "var(--card)",
                  borderWidth: 1,
                  borderColor: "var(--border)",
                }}
              >
                <Poster movie={current!} showTitle />
              </motion.div>
            </AnimatePresence>
          </div>
        )}

        <div className="flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => vote(false)}
            disabled={!current}
            className="h-14 w-14 rounded-full flex items-center justify-center transition-transform active:scale-90 disabled:opacity-40"
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
          <button
            type="button"
            onClick={skip}
            disabled={!current}
            className="h-10 px-3 rounded-full flex items-center gap-1.5 text-xs font-medium disabled:opacity-40"
            style={{
              backgroundColor: "transparent",
              color: "var(--muted-foreground)",
              borderWidth: 1,
              borderColor: "var(--border)",
            }}
            aria-label="Skip this movie"
          >
            <SkipForward className="h-3.5 w-3.5" />
            Skip
          </button>
          <button
            type="button"
            onClick={() => vote(true)}
            disabled={!current}
            className="h-14 w-14 rounded-full flex items-center justify-center transition-transform active:scale-90 disabled:opacity-40"
            style={{ backgroundColor: "var(--tab-collaborative)", color: "white" }}
            aria-label="Like"
          >
            <ThumbsUp className="h-5 w-5" />
          </button>
        </div>

        {canFinish && (
          <button
            type="button"
            onClick={finish}
            disabled={finishing}
            className="flex items-center justify-center gap-2 py-3 rounded-lg text-sm font-semibold text-white transition-shadow disabled:opacity-60"
            style={{
              backgroundColor: "var(--tab-collaborative)",
              boxShadow: "var(--shadow-glow-purple)",
            }}
          >
            {finishing && <Loader2 className="h-4 w-4 animate-spin" />}
            Done — get my recommendations
            <ArrowRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

function Poster({ movie, showTitle }: { movie: TrendingMovie; showTitle?: boolean }) {
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
            background: "linear-gradient(to top, oklch(0 0 0 / 0.85), oklch(0 0 0 / 0.1))",
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
