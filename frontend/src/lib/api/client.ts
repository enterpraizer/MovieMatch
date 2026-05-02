import createClient, { type Middleware } from "openapi-fetch";

const TOKEN_KEY = "mm_access_token";
const REFRESH_KEY = "mm_refresh_token";

const BASE_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return Date.now() / 1000 > payload.exp;
  } catch {
    return true;
  }
}

async function refreshTokens(): Promise<boolean> {
  const refreshToken = typeof window !== "undefined"
    ? localStorage.getItem(REFRESH_KEY)
    : null;
  if (!refreshToken) return false;

  try {
    const resp = await fetch(`${BASE_URL}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) return false;

    const data = await resp.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = getToken();
    if (token && !isTokenExpired(token)) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },

  async onResponse({ request, response }) {
    if (response.status !== 401) return response;

    const refreshed = await refreshTokens();
    if (!refreshed) {
      clearTokens();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return response;
    }

    const newToken = getToken();
    if (newToken) {
      const retryRequest = request.clone();
      retryRequest.headers.set("Authorization", `Bearer ${newToken}`);
      return fetch(retryRequest);
    }
    return response;
  },
};

export const api = createClient({ baseUrl: BASE_URL });
api.use(authMiddleware);
