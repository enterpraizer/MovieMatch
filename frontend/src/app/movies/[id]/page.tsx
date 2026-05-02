import { Film, Star, Clock } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { MovieActions } from "@/components/features/movie-detail/MovieActions";
import { BackButton } from "@/components/common/BackButton";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TMDB_IMG = "https://image.tmdb.org/t/p";

interface MovieDetail {
  id: number;
  title: string;
  year: number | null;
  avg_rating: number | null;
  rating_count: number;
  genres: string[];
  poster_url: string | null;
  description: string | null;
  runtime_minutes: number | null;
  imdb_id: string | null;
  credits: {
    person: { id: number; name: string; profile_path: string | null };
    role: string;
    character_name: string | null;
    order_index: number | null;
  }[];
}

async function getMovie(id: string): Promise<MovieDetail | null> {
  try {
    const resp = await fetch(`${API_URL}/v1/movies/${id}`, {
      next: { revalidate: 3600 },
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const movie = await getMovie(id);
  if (!movie) return { title: "Movie not found — MovieMatch" };

  return {
    title: `${movie.title}${movie.year ? ` (${movie.year})` : ""} — MovieMatch`,
    description: movie.description?.slice(0, 160) ?? `Details for ${movie.title}`,
    openGraph: {
      title: movie.title,
      description: movie.description ?? undefined,
      images: movie.poster_url ? [movie.poster_url] : [],
      type: "website",
    },
  };
}

export default async function MoviePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const movie = await getMovie(id);

  if (!movie) {
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center gap-4"
        style={{ backgroundColor: "var(--background)" }}
      >
        <Film className="h-16 w-16" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
        <h1 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
          Movie not found
        </h1>
        <Link href="/" className="text-sm underline" style={{ color: "var(--tab-collaborative)" }}>
          Back to home
        </Link>
      </div>
    );
  }

  const directors = movie.credits.filter((c) => c.role === "director");
  const actors = movie.credits.filter((c) => c.role === "actor");

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      {/* Backdrop blur */}
      <div className="relative h-64 md:h-80 overflow-hidden">
        {movie.poster_url && (
          <Image
            src={movie.poster_url}
            alt=""
            fill
            className="object-cover blur-2xl scale-110 opacity-30"
            priority
          />
        )}
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(to bottom, oklch(0.13 0.005 260 / 0.4), var(--background))",
          }}
        />
      </div>

      <div className="max-w-5xl mx-auto px-4 -mt-40 md:-mt-52 relative z-10">
        <div className="flex flex-col md:flex-row gap-6">
          {/* Poster */}
          <div className="shrink-0 w-48 md:w-56 mx-auto md:mx-0">
            <div
              className="aspect-[2/3] rounded-xl overflow-hidden shadow-2xl"
              style={{ backgroundColor: "var(--card)" }}
            >
              {movie.poster_url ? (
                <Image
                  src={movie.poster_url}
                  alt={`${movie.title} poster`}
                  width={224}
                  height={336}
                  className="object-cover w-full h-full"
                  priority
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Film className="h-16 w-16" style={{ color: "var(--muted-foreground)", opacity: 0.3 }} />
                </div>
              )}
            </div>
          </div>

          {/* Details */}
          <div className="flex-1 flex flex-col gap-3">
            <h1 className="text-2xl md:text-3xl font-bold" style={{ color: "var(--foreground)" }}>
              {movie.title}
              {movie.year && (
                <span className="font-normal ml-2" style={{ color: "var(--muted-foreground)" }}>
                  ({movie.year})
                </span>
              )}
            </h1>

            <div className="flex flex-wrap items-center gap-3">
              {movie.avg_rating != null && (
                <div className="flex items-center gap-1">
                  <Star className="h-4 w-4" style={{ fill: "var(--accent)", color: "var(--accent)" }} />
                  <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                    {movie.avg_rating.toFixed(1)}
                  </span>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    ({movie.rating_count})
                  </span>
                </div>
              )}
              {movie.runtime_minutes && (
                <div className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {Math.floor(movie.runtime_minutes / 60)}h {movie.runtime_minutes % 60}m
                  </span>
                </div>
              )}
            </div>

            {movie.genres.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {movie.genres.map((g) => (
                  <span
                    key={g}
                    className="px-2.5 py-0.5 rounded-full text-xs font-medium"
                    style={{
                      backgroundColor: "var(--secondary)",
                      color: "var(--secondary-foreground)",
                    }}
                  >
                    {g}
                  </span>
                ))}
              </div>
            )}

            {directors.length > 0 && (
              <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
                Directed by{" "}
                <span style={{ color: "var(--foreground)" }}>
                  {directors.map((d) => d.person.name).join(", ")}
                </span>
              </p>
            )}

            {movie.description && (
              <p className="text-sm leading-relaxed" style={{ color: "var(--muted-foreground)" }}>
                {movie.description}
              </p>
            )}

            <MovieActions movieId={movie.id} title={movie.title} year={movie.year} />
          </div>
        </div>

        {/* Cast */}
        {actors.length > 0 && (
          <section className="mt-8">
            <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>
              Cast
            </h2>
            <div className="flex gap-3 overflow-x-auto pb-2">
              {actors.map((c) => (
                <div
                  key={`${c.person.id}-${c.role}`}
                  className="shrink-0 flex flex-col items-center gap-1.5 w-20"
                >
                  <div
                    className="w-14 h-14 rounded-full overflow-hidden"
                    style={{ backgroundColor: "var(--secondary)" }}
                  >
                    {c.person.profile_path ? (
                      <Image
                        src={`${TMDB_IMG}/w185${c.person.profile_path}`}
                        alt={c.person.name}
                        width={56}
                        height={56}
                        className="object-cover w-full h-full"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-lg" style={{ color: "var(--muted-foreground)" }}>
                        {c.person.name[0]}
                      </div>
                    )}
                  </div>
                  <span
                    className="text-xs text-center leading-tight line-clamp-2"
                    style={{ color: "var(--foreground)" }}
                  >
                    {c.person.name}
                  </span>
                  {c.character_name && (
                    <span
                      className="text-[10px] text-center leading-tight line-clamp-1"
                      style={{ color: "var(--muted-foreground)" }}
                    >
                      {c.character_name}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="mt-8 pb-8">
          <BackButton
            fallbackHref="/"
            className="text-sm cursor-pointer"
            style={{ color: "var(--tab-collaborative)" }}
          >
            ← Back
          </BackButton>
        </div>
      </div>
    </div>
  );
}
