"use client";

import { useCallback, useRef } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Star, Search, Camera, Library, UserCircle2 } from "lucide-react";
import { useUIStore } from "@/store/ui-store";
import { CollaborativeTab, SearchTab, EmotionTab } from "@/components/features/tabs";

const POSTER_COLORS = [
  "#1a1520", "#201828", "#18202a", "#221a1e",
  "#1c2028", "#261c22", "#1a2420", "#201a26",
  "#1e1a28", "#28201a", "#1a2024", "#221e1a",
];

type TabId = "collaborative" | "search" | "emotion";

const TABS: { id: TabId; label: string; icon: typeof Star; color: string }[] = [
  { id: "collaborative", label: "By Ratings", icon: Star, color: "var(--tab-collaborative)" },
  { id: "search", label: "By Description", icon: Search, color: "var(--tab-search)" },
  { id: "emotion", label: "By Mood", icon: Camera, color: "var(--tab-emotion)" },
];

export default function Home() {
  const activeTab = useUIStore((s) => s.activeTab);
  const setActiveTab = useUIStore((s) => s.setActiveTab);
  const navRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const idx = TABS.findIndex((t) => t.id === activeTab);
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setActiveTab(TABS[(idx + 1) % TABS.length].id);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setActiveTab(TABS[(idx - 1 + TABS.length) % TABS.length].id);
      }
    },
    [activeTab, setActiveTab]
  );

  return (
    <div className="min-h-screen flex flex-col">
      {/* Hero */}
      <section className="relative h-48 md:h-64 overflow-hidden">
        <div className="absolute inset-0 grid grid-cols-4 grid-rows-3 blur-sm opacity-20 scale-110">
          {POSTER_COLORS.map((color, i) => (
            <div key={i} style={{ backgroundColor: color }} />
          ))}
        </div>
        <div
          className="absolute inset-0 z-10"
          style={{
            background: "linear-gradient(to bottom, oklch(0 0 0 / 0.3), var(--background))",
          }}
        />
        <div className="absolute top-3 right-3 sm:right-4 z-30 flex items-center gap-2">
          <Link
            href="/browse"
            aria-label="Browse all movies"
            className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-medium backdrop-blur-md transition-colors"
            style={{
              backgroundColor: "oklch(0.18 0.008 260 / 0.7)",
              color: "var(--foreground)",
              borderWidth: 1,
              borderColor: "var(--border)",
            }}
          >
            <Library className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Browse all movies</span>
            <span className="sm:hidden">Browse</span>
          </Link>
          <Link
            href="/profile"
            aria-label="Profile"
            className="flex items-center justify-center h-8 w-8 rounded-lg backdrop-blur-md transition-colors"
            style={{
              backgroundColor: "oklch(0.18 0.008 260 / 0.7)",
              color: "var(--foreground)",
              borderWidth: 1,
              borderColor: "var(--border)",
            }}
          >
            <UserCircle2 className="h-4 w-4" />
          </Link>
        </div>
        <div className="relative z-20 flex flex-col items-center justify-center h-full text-center px-4">
          <h1
            className="text-3xl md:text-4xl font-bold tracking-tight"
            style={{ color: "var(--foreground)" }}
          >
            Find Your Perfect Movie
          </h1>
          <p className="mt-1.5 text-sm md:text-base" style={{ color: "var(--muted-foreground)" }}>
            AI-powered recommendations — by ratings, description, or mood
          </p>
        </div>
      </section>

      {/* Tab bar */}
      <div
        className="sticky top-0 z-40 backdrop-blur-lg"
        style={{
          backgroundColor: "oklch(0.13 0.005 260 / 0.9)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="max-w-6xl mx-auto px-4">
          <nav
            ref={navRef}
            role="tablist"
            className="flex items-center gap-1 py-1.5 overflow-x-auto"
            onKeyDown={handleKeyDown}
          >
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={isActive}
                  tabIndex={isActive ? 0 : -1}
                  onClick={() => setActiveTab(tab.id)}
                  className="relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all duration-200"
                  style={{
                    color: isActive ? tab.color : "var(--muted-foreground)",
                    backgroundColor: isActive ? `color-mix(in oklch, ${tab.color} 12%, transparent)` : "transparent",
                  }}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                  {isActive && (
                    <motion.div
                      layoutId="tab-indicator"
                      className="absolute bottom-0 inset-x-2 h-0.5 rounded-full"
                      style={{ backgroundColor: tab.color }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Tab content */}
      <main className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            {activeTab === "collaborative" && <CollaborativeTab />}
            {activeTab === "search" && <SearchTab />}
            {activeTab === "emotion" && <EmotionTab />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
