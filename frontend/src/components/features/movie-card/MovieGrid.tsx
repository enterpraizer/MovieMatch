"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Film } from "lucide-react";
import { MovieCard, type MovieCardMovie } from "./MovieCard";
import { MovieCardSkeleton } from "./MovieCardSkeleton";

interface MovieGridProps {
  movies: MovieCardMovie[];
  isLoading?: boolean;
  emptyMessage?: string;
  emptyIcon?: LucideIcon;
  showScore?: boolean;
  onMovieClick?: (movieId: number) => void;
}

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

export function MovieGrid({
  movies,
  isLoading = false,
  emptyMessage = "No movies found",
  emptyIcon: EmptyIcon = Film,
  showScore = false,
  onMovieClick,
}: MovieGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-4">
        {Array.from({ length: 10 }).map((_, i) => (
          <MovieCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (movies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <EmptyIcon
          className="h-16 w-16"
          style={{ color: "var(--muted-foreground)", opacity: 0.3 }}
        />
        <p
          className="text-sm text-center max-w-xs"
          style={{ color: "var(--muted-foreground)" }}
        >
          {emptyMessage}
        </p>
      </div>
    );
  }

  return (
    <motion.div
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-4"
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      <AnimatePresence mode="popLayout">
        {movies.map((movie, index) => (
          <motion.div key={movie.movie_id} variants={itemVariants}>
            <MovieCard
              movie={movie}
              showScore={showScore}
              priority={index < 5}
              onCardClick={onMovieClick}
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </motion.div>
  );
}
