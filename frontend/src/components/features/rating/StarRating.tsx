"use client";

import { useEffect, useState } from "react";
import { Star, Check } from "lucide-react";
import { useRatingsStore } from "@/store/ratings-store";
import { cn } from "@/lib/utils";

interface StarRatingProps {
  movieId: number;
  movieTitle: string;
  compact?: boolean;
  className?: string;
}

export function StarRating({
  movieId,
  movieTitle,
  compact = false,
  className,
}: StarRatingProps) {
  const storeRating = useRatingsStore((s) => s.ratings[movieId] ?? 0);
  const setRating = useRatingsStore((s) => s.setRating);
  const [hoverRating, setHoverRating] = useState(0);
  const [justRated, setJustRated] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const currentRating = mounted ? storeRating : 0;
  const displayRating = hoverRating || currentRating;
  const starSize = compact ? "h-4 w-4" : "h-5 w-5";

  function handleClick(starIndex: number, isLeftHalf: boolean) {
    const score = isLeftHalf ? starIndex - 0.5 : starIndex;
    setRating(movieId, score);
    setJustRated(true);
    setTimeout(() => setJustRated(false), 600);
  }

  if (justRated) {
    return (
      <div
        className={cn(
          "flex items-center gap-1",
          className
        )}
        style={{ animation: "score-badge-pop 0.3s ease-out" }}
      >
        <Check className={cn(starSize, "text-green-400")} />
        <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
          {currentRating.toFixed(1)}
        </span>
      </div>
    );
  }

  return (
    <div
      className={cn("flex items-center gap-0.5", className)}
      role="radiogroup"
      aria-label={`Rate ${movieTitle}`}
      onMouseLeave={() => setHoverRating(0)}
    >
      {[1, 2, 3, 4, 5].map((starIndex) => {
        const filled = displayRating >= starIndex;
        const halfFilled =
          !filled && displayRating >= starIndex - 0.5;

        return (
          <div
            key={starIndex}
            className="relative cursor-pointer"
            data-star={starIndex}
          >
            {/* Left half */}
            <div
              className="absolute inset-0 w-1/2 z-10"
              onMouseEnter={() => setHoverRating(starIndex - 0.5)}
              onClick={() => handleClick(starIndex, true)}
              role="radio"
              aria-checked={currentRating === starIndex - 0.5}
              aria-label={`${starIndex - 0.5} stars`}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleClick(starIndex, true);
                }
              }}
            />
            {/* Right half */}
            <div
              className="absolute inset-0 left-1/2 w-1/2 z-10"
              onMouseEnter={() => setHoverRating(starIndex)}
              onClick={() => handleClick(starIndex, false)}
              role="radio"
              aria-checked={currentRating === starIndex}
              aria-label={`${starIndex} stars`}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleClick(starIndex, false);
                }
              }}
            />
            <Star
              className={cn(
                starSize,
                "transition-colors duration-100",
                filled
                  ? "fill-[var(--accent)] text-[var(--accent)]"
                  : halfFilled
                    ? "text-[var(--accent)]"
                    : "text-[var(--muted-foreground)]/30"
              )}
              style={
                halfFilled
                  ? {
                      clipPath: "inset(0 50% 0 0)",
                      fill: "var(--accent)",
                      position: "absolute",
                    }
                  : undefined
              }
            />
            {halfFilled && (
              <Star
                className={cn(starSize, "text-[var(--muted-foreground)]/30")}
              />
            )}
            {!halfFilled && (
              <span className="invisible">
                <Star className={starSize} />
              </span>
            )}
          </div>
        );
      })}

      {currentRating > 0 && !compact && (
        <span
          className="text-xs ml-1 tabular-nums"
          style={{ color: "var(--muted-foreground)" }}
        >
          {currentRating.toFixed(1)}
        </span>
      )}
    </div>
  );
}
