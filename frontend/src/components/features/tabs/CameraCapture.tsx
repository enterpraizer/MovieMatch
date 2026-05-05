"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Upload, X, AlertCircle } from "lucide-react";

type Mode = "select" | "camera" | "upload";

interface CameraCaptureProps {
  onImageCaptured: (blob: Blob) => void;
  disabled?: boolean;
}

const MAX_SIZE = 5 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function CameraCapture({ onImageCaptured, disabled }: CameraCaptureProps) {
  const [mode, setMode] = useState<Mode>("select");
  const [error, setError] = useState<string | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const stopCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      setStream(null);
    }
  }, [stream]);

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  const startCamera = async () => {
    setError(null);
    setMode("camera");
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch {
      setError("Camera access denied. Check browser permissions.");
      setMode("select");
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    stopCamera();

    canvas.toBlob(
      (blob) => {
        if (blob) onImageCaptured(blob);
      },
      "image/jpeg",
      0.85
    );
    setMode("select");
  };

  const handleFile = (file: File) => {
    setError(null);
    if (!ALLOWED_TYPES.has(file.type)) {
      setError("Use JPEG, PNG, or WebP images only.");
      return;
    }
    if (file.size > MAX_SIZE) {
      setError("Photo must be under 5 MB.");
      return;
    }
    onImageCaptured(file);
    setMode("select");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  if (mode === "camera") {
    return (
      <div className="flex flex-col items-center gap-3">
        <div className="relative rounded-xl overflow-hidden" style={{ backgroundColor: "var(--card)" }}>
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full max-w-sm aspect-[4/3] object-cover"
          />
          <div className="absolute bottom-3 inset-x-0 flex justify-center gap-3">
            <button
              onClick={capturePhoto}
              className="h-14 w-14 rounded-full border-4 border-white/80 transition-transform active:scale-90"
              style={{ backgroundColor: "var(--tab-emotion)" }}
              disabled={disabled}
            />
            <button
              onClick={() => { stopCamera(); setMode("select"); }}
              className="flex items-center justify-center h-10 w-10 rounded-full self-end"
              style={{ backgroundColor: "var(--secondary)" }}
            >
              <X className="h-4 w-4" style={{ color: "var(--foreground)" }} />
            </button>
          </div>
        </div>
        <canvas ref={canvasRef} className="hidden" />
      </div>
    );
  }

  if (mode === "upload") {
    return (
      <div className="flex flex-col items-center gap-3">
        <div
          className={`w-full max-w-sm aspect-[4/3] rounded-xl flex flex-col items-center justify-center gap-3 transition-colors cursor-pointer ${dragOver ? "ring-2" : ""}`}
          style={{
            backgroundColor: "var(--card)",
            borderWidth: 2,
            borderStyle: "dashed",
            borderColor: dragOver ? "var(--tab-emotion)" : "var(--border)",
            outlineColor: "var(--tab-emotion)",
          }}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <Upload className="h-8 w-8" style={{ color: "var(--muted-foreground)" }} />
          <p className="text-sm text-center px-4" style={{ color: "var(--muted-foreground)" }}>
            Drop a photo here, or click to browse
          </p>
          <p className="text-xs" style={{ color: "var(--subtle-foreground)" }}>
            JPEG, PNG, WebP · Max 5 MB
          </p>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <button
          onClick={() => setMode("select")}
          className="text-xs underline"
          style={{ color: "var(--muted-foreground)" }}
        >
          Back
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      {error && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm w-full max-w-sm"
          style={{ backgroundColor: "oklch(0.25 0.05 25)", color: "oklch(0.8 0.15 25)" }}
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}
      <div className="flex gap-3">
        <button
          onClick={startCamera}
          disabled={disabled}
          className="flex flex-col items-center gap-2 px-6 py-4 rounded-xl transition-colors"
          style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
        >
          <Camera className="h-8 w-8" style={{ color: "var(--tab-emotion)" }} />
          <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>Take a selfie</span>
        </button>
        <button
          onClick={() => { setError(null); setMode("upload"); }}
          disabled={disabled}
          className="flex flex-col items-center gap-2 px-6 py-4 rounded-xl transition-colors"
          style={{ backgroundColor: "var(--card)", borderWidth: 1, borderColor: "var(--border)" }}
        >
          <Upload className="h-8 w-8" style={{ color: "var(--tab-emotion)" }} />
          <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>Upload photo</span>
        </button>
      </div>
    </div>
  );
}
