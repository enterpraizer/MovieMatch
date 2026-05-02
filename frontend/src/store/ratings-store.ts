import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { api, getToken } from "@/lib/api/client";

interface RatingsState {
  ratings: Record<number, number>;
  setRating: (movieId: number, score: number) => void;
  removeRating: (movieId: number) => void;
  clearRatings: () => Promise<void>;
  ratingCount: () => number;
  hydrateFromServer: () => Promise<void>;
}

// Fire-and-forget sync so rating clicks aren't blocked on the network.
// Unauthenticated users still get local-only behaviour (useful for browsing
// before signup); their store is pushed up once they log in.
function syncPut(movieId: number, score: number): void {
  if (typeof window === "undefined" || !getToken()) return;
  void (api as unknown as {
    POST: (path: string, init: { body: unknown }) => Promise<unknown>;
  }).POST("/v1/ratings", { body: { movie_id: movieId, score } });
}

function syncDelete(movieId: number): void {
  if (typeof window === "undefined" || !getToken()) return;
  void (api as unknown as {
    DELETE: (path: string) => Promise<unknown>;
  }).DELETE(`/v1/ratings/${movieId}`);
}

export const useRatingsStore = create<RatingsState>()(
  devtools(
    persist(
      (set, get) => ({
        ratings: {},

        setRating: (movieId, score) => {
          set(
            (state) => ({
              ratings: { ...state.ratings, [movieId]: score },
            }),
            false,
            "setRating"
          );
          syncPut(movieId, score);
        },

        removeRating: (movieId) => {
          set(
            (state) => {
              const { [movieId]: _, ...rest } = state.ratings;
              return { ratings: rest };
            },
            false,
            "removeRating"
          );
          syncDelete(movieId);
        },

        clearRatings: async () => {
          set({ ratings: {} }, false, "clearRatings");
          // Wipe server-side in a single atomic request, then return.
          // Callers await this before re-querying recommendations so the
          // /collaborative DB fallback doesn't resurrect old ratings.
          if (typeof window !== "undefined" && getToken()) {
            try {
              await (api as unknown as {
                DELETE: (path: string) => Promise<unknown>;
              }).DELETE("/v1/ratings/me");
            } catch {
              /* best-effort: local store already cleared */
            }
          }
        },

        ratingCount: () => Object.keys(get().ratings).length,

        hydrateFromServer: async () => {
          if (typeof window === "undefined" || !getToken()) return;
          try {
            const resp = await (api as unknown as {
              GET: (
                path: string,
                init?: { params?: { query?: Record<string, unknown> } },
              ) => Promise<{ data?: { items?: Array<{ movie_id: number; score: number }> } }>;
            }).GET("/v1/ratings/me", { params: { query: { limit: 500 } } });
            const items = resp.data?.items ?? [];
            const serverRatings: Record<number, number> = {};
            for (const r of items) {
              serverRatings[r.movie_id] = r.score;
            }
            // Any server-side ratings ⇒ user is past onboarding, even if this
            // is their first time on a new browser. Mark done so the /onboarding
            // route never ambushes returning users.
            if (items.length > 0) {
              window.localStorage.setItem("mm-onboarding-done", "1");
            }
            // Merge: local takes precedence over server (user's in-flight
            // edits that haven't synced yet win) but we fill in anything
            // missing from the server.
            set(
              (state) => ({ ratings: { ...serverRatings, ...state.ratings } }),
              false,
              "hydrateFromServer",
            );
            // Push any local ratings the server doesn't know about.
            const current = get().ratings;
            for (const [mid, score] of Object.entries(current)) {
              if (serverRatings[Number(mid)] !== score) {
                syncPut(Number(mid), score);
              }
            }
          } catch {
            // network failure is fine — we already have local state
          }
        },
      }),
      { name: "mm-ratings" }
    ),
    { name: "RatingsStore" }
  )
);
