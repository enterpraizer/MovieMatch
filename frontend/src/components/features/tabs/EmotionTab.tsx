"use client";

import { useState } from "react";
import { ShieldCheck, RefreshCw } from "lucide-react";
import { MovieGrid, type MovieCardMovie } from "@/components/features/movie-card";
import { CameraCapture } from "./CameraCapture";
import { EmotionResult } from "./EmotionResult";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Step = "capture" | "detecting" | "results" | "error";

interface EmotionData {
  emotion: string;
  confidence: number;
  all_scores: Record<string, number>;
  message: string;
}

interface RecoResponse {
  items: MovieCardMovie[];
  emotion: string | null;
  emotion_confidence: number | null;
  emotion_message: string | null;
}

const ERROR_MESSAGES: Record<string, string> = {
  FACE_NOT_DETECTED: "No face found. Try a well-lit selfie with your face clearly visible.",
  IMAGE_TOO_LARGE: "Photo is too large. Please use a smaller image (max 5 MB).",
  ML_SERVICE_UNAVAILABLE: "Service temporarily unavailable. Try again in a moment.",
};

export function EmotionTab() {
  const [step, setStep] = useState<Step>("capture");
  const [emotionData, setEmotionData] = useState<EmotionData | null>(null);
  const [movies, setMovies] = useState<MovieCardMovie[]>([]);
  const [errorMessage, setErrorMessage] = useState("");

  const handleImageCaptured = async (blob: Blob) => {
    setStep("detecting");
    setErrorMessage("");
    try {
      const token = typeof window !== "undefined"
        ? localStorage.getItem("mm_access_token")
        : null;

      const form = new FormData();
      form.append("image", blob, "capture.jpg");

      const resp = await fetch(`${API_URL}/v1/recommendations/emotion`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const code = body?.error?.code ?? body?.detail?.code ?? "";
        throw new Error(ERROR_MESSAGES[code] ?? `Detection failed (${resp.status})`);
      }

      const data: RecoResponse & { emotion_data?: EmotionData } = await resp.json();
      setEmotionData({
        emotion: data.emotion ?? "neutral",
        confidence: data.emotion_confidence ?? 0,
        all_scores: {},
        message: data.emotion_message ?? "",
      });
      setMovies(data.items ?? []);
      setStep("results");
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : "Something went wrong");
      setStep("error");
    }
  };

  const handleReset = () => {
    setStep("capture");
    setEmotionData(null);
    setMovies([]);
    setErrorMessage("");
  };

  return (
    <div className="flex flex-col gap-6 tab-content-enter">
      {/* Privacy notice */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs mx-auto"
        style={{
          backgroundColor: "var(--card)",
          color: "var(--muted-foreground)",
        }}
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--tab-emotion)" }} />
        Processed instantly, never stored
      </div>

      {step === "capture" && (
        <CameraCapture onImageCaptured={handleImageCaptured} />
      )}

      {step === "detecting" && (
        <div className="flex flex-col items-center gap-4 py-8">
          <div
            className="h-16 w-16 rounded-full animate-pulse"
            style={{ backgroundColor: "var(--tab-emotion)", opacity: 0.3 }}
          />
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            Analyzing your expression...
          </p>
        </div>
      )}

      {step === "error" && (
        <div className="flex flex-col items-center gap-4 py-8">
          <div
            className="p-4 rounded-lg text-sm text-center max-w-sm"
            style={{
              backgroundColor: "oklch(0.25 0.05 25)",
              color: "oklch(0.8 0.15 25)",
            }}
          >
            {errorMessage}
          </div>
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium"
            style={{
              backgroundColor: "var(--tab-emotion)",
              color: "white",
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Try again
          </button>
        </div>
      )}

      {step === "results" && emotionData && (
        <>
          <EmotionResult
            emotion={emotionData.emotion}
            confidence={emotionData.confidence}
            allScores={emotionData.all_scores}
            message={emotionData.message}
          />

          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
              Movies for your mood
            </h2>
            <button
              onClick={handleReset}
              className="text-xs underline"
              style={{ color: "var(--muted-foreground)" }}
            >
              Try again
            </button>
          </div>

          <MovieGrid
            movies={movies}
            emptyMessage="No movies found for this mood. Try again!"
          />
        </>
      )}
    </div>
  );
}
