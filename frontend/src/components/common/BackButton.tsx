"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";

interface BackButtonProps {
  fallbackHref?: string;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

export function BackButton({
  fallbackHref = "/",
  className,
  style,
  children,
}: BackButtonProps) {
  const router = useRouter();
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    // history.length grows on every client-side navigation (Next.js <Link>
    // updates window.history even though it leaves document.referrer untouched).
    // length === 1 means this tab was opened directly at this URL, so there's
    // nowhere to go back to; fall back to the explicit href.
    setCanGoBack(window.history.length > 1);
  }, []);

  if (canGoBack) {
    return (
      <button
        type="button"
        onClick={() => router.back()}
        className={className}
        style={style}
      >
        {children}
      </button>
    );
  }

  return (
    <Link href={fallbackHref} className={className} style={style}>
      {children}
    </Link>
  );
}
