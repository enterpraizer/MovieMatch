"use client";

import { motion } from "framer-motion";

const EMOTION_EMOJI: Record<string, string> = {
  happy: "😊",
  sad: "😢",
  angry: "😠",
  fear: "😨",
  surprise: "😲",
  disgust: "🤢",
  neutral: "😐",
};

const EMOTION_COLORS: Record<string, string> = {
  happy: "oklch(0.82 0.16 100)",
  sad: "oklch(0.62 0.15 260)",
  angry: "oklch(0.62 0.22 25)",
  fear: "oklch(0.68 0.18 290)",
  surprise: "oklch(0.72 0.14 210)",
  disgust: "oklch(0.55 0.15 145)",
  neutral: "oklch(0.65 0.01 260)",
};

interface EmotionResultProps {
  emotion: string;
  confidence: number;
  allScores: Record<string, number>;
  message: string;
}

export function EmotionResult({
  emotion,
  confidence,
  allScores,
  message,
}: EmotionResultProps) {
  const emoji = EMOTION_EMOJI[emotion] ?? "🎬";
  const sorted = Object.entries(allScores).sort(([, a], [, b]) => b - a);
  const maxScore = Math.max(...Object.values(allScores), 0.01);

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Emoji + label */}
      <motion.div
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 15 }}
        className="text-6xl"
      >
        {emoji}
      </motion.div>

      <div className="text-center">
        <p className="text-lg font-semibold capitalize" style={{ color: "var(--foreground)" }}>
          {emotion}
        </p>
        <p className="text-xs tabular-nums" style={{ color: "var(--muted-foreground)" }}>
          {Math.round(confidence * 100)}% confidence
        </p>
        <p className="text-sm mt-1" style={{ color: "var(--muted-foreground)" }}>
          {message}
        </p>
      </div>

      {/* Score bars */}
      <div className="w-full max-w-xs flex flex-col gap-1.5">
        {sorted.map(([key, score]) => {
          const isDetected = key === emotion;
          const width = (score / maxScore) * 100;
          const color = isDetected
            ? (EMOTION_COLORS[key] ?? "var(--primary)")
            : "var(--muted-foreground)";

          return (
            <div key={key} className="flex items-center gap-2">
              <span
                className="text-xs w-16 text-right capitalize truncate"
                style={{
                  color: isDetected ? color : "var(--muted-foreground)",
                  fontWeight: isDetected ? 600 : 400,
                }}
              >
                {key}
              </span>
              <div
                className="flex-1 h-2 rounded-full overflow-hidden"
                style={{ backgroundColor: "var(--secondary)" }}
              >
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${width}%` }}
                  transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
                  className="h-full rounded-full"
                  style={{
                    backgroundColor: isDetected ? color : "var(--muted-foreground)",
                    opacity: isDetected ? 1 : 0.3,
                  }}
                />
              </div>
              <span
                className="text-xs w-8 tabular-nums"
                style={{ color: "var(--subtle-foreground)" }}
              >
                {Math.round(score * 100)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
