import { create } from "zustand";
import { devtools } from "zustand/middleware";

type TabId = "collaborative" | "search" | "emotion";

interface SearchFilters {
  year_from: number | null;
  year_to: number | null;
  min_rating: number | null;
  genres: string[] | null;
}

interface EmotionResult {
  emotion: string;
  confidence: number;
  message: string;
}

interface UIState {
  activeTab: TabId;
  searchQuery: string;
  searchFilters: SearchFilters;
  emotionResult: EmotionResult | null;
  capturedImagePreview: string | null;

  setActiveTab: (tab: TabId) => void;
  setSearchQuery: (query: string) => void;
  setSearchFilters: (filters: Partial<SearchFilters>) => void;
  setEmotionResult: (result: EmotionResult | null) => void;
  setCapturedImagePreview: (url: string | null) => void;
  clearEmotionState: () => void;
}

const defaultFilters: SearchFilters = {
  year_from: null,
  year_to: null,
  min_rating: null,
  genres: null,
};

export const useUIStore = create<UIState>()(
  devtools(
    (set) => ({
      activeTab: "collaborative",
      searchQuery: "",
      searchFilters: { ...defaultFilters },
      emotionResult: null,
      capturedImagePreview: null,

      setActiveTab: (tab) =>
        set(
          (state) => {
            // Leaving the Search tab for a different main tab means the user
            // has consciously moved on — wipe the persisted search state so
            // they don't return to stale results. Cross-route navigations
            // (/movies/{id}, /profile, /browse) don't change activeTab, so
            // those still restore their search on Back.
            if (
              state.activeTab === "search" &&
              tab !== "search" &&
              typeof window !== "undefined"
            ) {
              sessionStorage.removeItem("mm-search-state");
            }
            return { activeTab: tab };
          },
          false,
          "setActiveTab",
        ),

      setSearchQuery: (query) =>
        set({ searchQuery: query }, false, "setSearchQuery"),

      setSearchFilters: (filters) =>
        set(
          (state) => ({
            searchFilters: { ...state.searchFilters, ...filters },
          }),
          false,
          "setSearchFilters"
        ),

      setEmotionResult: (result) =>
        set({ emotionResult: result }, false, "setEmotionResult"),

      setCapturedImagePreview: (url) =>
        set({ capturedImagePreview: url }, false, "setCapturedImagePreview"),

      clearEmotionState: () =>
        set(
          { emotionResult: null, capturedImagePreview: null },
          false,
          "clearEmotionState"
        ),
    }),
    { name: "UIStore" }
  )
);
