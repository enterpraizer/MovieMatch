"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import Link from "next/link";
import { Star, Film, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface MovieCardMovie {
  movie_id: number;
  title: string;
  year: number | null;
  genres: string[];
  avg_rating: number | null;
  poster_url: string | null;
  score?: number;
  reason?: string;
}

interface MovieCardProps {
  movie: MovieCardMovie;
  showScore?: boolean;
  priority?: boolean;
  onCardClick?: (movieId: number) => void;
  className?: string;
}

function ScoreBadge({ score }: { score: number }) {
  const percent = Math.round(score * 100);
  const color =
    percent >= 80
      ? "bg-green-500/80"
      : percent >= 60
        ? "bg-yellow-500/80"
        : "bg-gray-500/80";
  return (
    <div
      className={`absolute top-2 right-2 ${color} text-white text-xs font-semibold
                  px-2 py-0.5 rounded-full backdrop-blur-sm z-10`}
      style={{ animation: "score-badge-pop 0.3s ease-out" }}
    >
      {percent}%
    </div>
  );
}

export function MovieCard({
  movie,
  showScore = false,
  priority = false,
  onCardClick,
  className = "",
}: MovieCardProps) {
  const [imgError, setImgError] = useState(false);

  const content = (
    <motion.article
      data-testid="movie-card"
      aria-label={`${movie.title}${movie.year ? ` (${movie.year})` : ""}`}
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      whileHover={{ y: -4, transition: { duration: 0.15 } }}
      className={`group relative flex flex-col overflow-hidden rounded-lg
                  cursor-pointer transition-colors duration-200 ${className}`}
      style={{
        backgroundColor: "var(--card)",
        borderWidth: 1,
        borderColor: "var(--border)",
      }}
      onClick={() => onCardClick?.(movie.movie_id)}
      tabIndex={onCardClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onCardClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onCardClick(movie.movie_id);
        }
      }}
      role={onCardClick ? "button" : undefined}
    >
      {/* Poster */}
      <div className="relative aspect-[2/3] overflow-hidden" style={{ backgroundColor: "var(--muted)" }}>
        {!imgError && movie.poster_url ? (
          <Image
            src={movie.poster_url}
            alt={`${movie.title} poster`}
            fill
            className="object-cover transition-transform duration-300 group-hover:scale-105"
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 18vw"
            priority={priority}
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <Film className="h-12 w-12" style={{ color: "var(--muted-foreground)", opacity: 0.4 }} />
          </div>
        )}

        {/* Bottom gradient overlay */}
        <div className="absolute inset-0 gradient-overlay-bottom opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

        {/* Match score badge — hidden when score is missing (popularity fallback) */}
        {showScore && movie.score !== undefined && movie.score !== null && (
          <ScoreBadge score={movie.score} />
        )}

        {/* Hover detail prompt */}
        <div className="absolute bottom-2 left-0 right-0 flex justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <span className="text-white text-xs font-medium bg-black/60 px-3 py-1 rounded-full">
            View details
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1.5 p-3 flex-1">
        <h3 className="font-medium text-sm leading-tight line-clamp-2" style={{ color: "var(--foreground)" }}>
          {movie.title}
          {movie.year && (
            <span className="font-normal ml-1" style={{ color: "var(--muted-foreground)" }}>
              ({movie.year})
            </span>
          )}
        </h3>

        {movie.genres.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {movie.genres.slice(0, 2).map((g) => (
              <Badge key={g} variant="secondary" size="sm">
                {g}
              </Badge>
            ))}
          </div>
        )}

        {movie.reason && (
          <div
            className="flex items-center gap-1 mt-1 text-[10px] italic line-clamp-1"
            style={{ color: "var(--muted-foreground)" }}
            title={movie.reason}
          >
            <Sparkles className="h-2.5 w-2.5 shrink-0" />
            <span className="truncate">{movie.reason}</span>
          </div>
        )}

        {movie.avg_rating != null && (
          <div className="flex items-center gap-1 mt-auto">
            <Star
              className="h-3 w-3"
              style={{ fill: "var(--accent)", color: "var(--accent)" }}
            />
            <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
              {movie.avg_rating.toFixed(1)}
            </span>
          </div>
        )}
      </div>
    </motion.article>
  );

  if (!onCardClick) {
    return (
      <Link href={`/movies/${movie.movie_id}`} className="contents">
        {content}
      </Link>
    );
  }
  return content;
}
