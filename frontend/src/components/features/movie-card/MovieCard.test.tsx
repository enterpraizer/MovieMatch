import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MovieCard, type MovieCardMovie } from "./MovieCard";

const baseMovie: MovieCardMovie = {
  movie_id: 42,
  title: "The Matrix",
  year: 1999,
  genres: ["Action", "Sci-Fi", "Thriller"],
  avg_rating: 4.6,
  poster_url: "https://image.tmdb.org/t/p/w500/poster.jpg",
  score: 0.87,
  reason: "Based on your ratings",
};

describe("MovieCard", () => {
  it("renders the movie title", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(screen.getByText(/The Matrix/)).toBeInTheDocument();
  });

  it("renders the year", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(screen.getByText("(1999)")).toBeInTheDocument();
  });

  it("shows at most 2 genres", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(screen.getByText("Action")).toBeInTheDocument();
    expect(screen.getByText("Sci-Fi")).toBeInTheDocument();
    expect(screen.queryByText("Thriller")).not.toBeInTheDocument();
  });

  it("shows score badge when showScore=true", () => {
    render(<MovieCard movie={baseMovie} showScore />);
    expect(screen.getByText("87%")).toBeInTheDocument();
  });

  it("hides score badge when showScore=false", () => {
    render(<MovieCard movie={baseMovie} showScore={false} />);
    expect(screen.queryByText("87%")).not.toBeInTheDocument();
  });

  it("calls onCardClick with correct id", () => {
    const onClick = vi.fn();
    render(<MovieCard movie={baseMovie} onCardClick={onClick} />);
    fireEvent.click(screen.getByTestId("movie-card"));
    expect(onClick).toHaveBeenCalledWith(42);
  });

  it("shows Film icon when no poster", () => {
    const noPosterMovie = { ...baseMovie, poster_url: null };
    render(<MovieCard movie={noPosterMovie} />);
    // Film icon from lucide-react is rendered as SVG
    const article = screen.getByTestId("movie-card");
    expect(article.querySelector("svg")).toBeInTheDocument();
  });

  it("has data-testid movie-card", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(screen.getByTestId("movie-card")).toBeInTheDocument();
  });

  it("has aria-label with title and year", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(
      screen.getByLabelText("The Matrix (1999)")
    ).toBeInTheDocument();
  });

  it("renders rating", () => {
    render(<MovieCard movie={baseMovie} />);
    expect(screen.getByText("4.6")).toBeInTheDocument();
  });
});
