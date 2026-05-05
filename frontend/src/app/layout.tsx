"use client";

import { Inter } from "next/font/google";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useRatingsStore } from "@/store/ratings-store";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
});

function RatingsHydrator() {
  const hydrate = useRatingsStore((s) => s.hydrateFromServer);
  useEffect(() => {
    void hydrate();
  }, [hydrate]);
  return null;
}

function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <title>MovieMatch — AI Movie Recommendations</title>
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=5"
        />
        <meta name="theme-color" content="#0b0910" />
        <meta
          name="description"
          content="Discover movies with AI: collaborative filtering, semantic search, and emotion detection."
        />
        <meta property="og:title" content="MovieMatch" />
        <meta
          property="og:description"
          content="AI-powered movie recommendations — by ratings, description, or mood."
        />
        <meta property="og:type" content="website" />
      </head>
      <body
        className={`${inter.variable} font-sans min-h-screen antialiased`}
        style={{
          backgroundColor: "var(--background)",
          color: "var(--foreground)",
        }}
      >
        <QueryProvider>
          <RatingsHydrator />
          {children}
        </QueryProvider>
      </body>
    </html>
  );
}
