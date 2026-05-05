import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
    get length() { return Object.keys(store).length; },
    key: (i: number) => Object.keys(store)[i] ?? null,
  };
})();
Object.defineProperty(globalThis, "localStorage", { value: localStorageMock });

vi.mock("next/image", () => ({
  default: (props: Record<string, unknown>) => {
    const { fill, priority, onError, ...rest } = props;
    return <img {...rest} data-fill={fill ? "true" : undefined} />;
  },
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

vi.mock("framer-motion", () => ({
  motion: {
    article: (props: Record<string, unknown>) => {
      const {
        whileHover,
        initial,
        animate,
        transition,
        layout,
        variants,
        ...rest
      } = props;
      return <article {...rest} />;
    },
    div: (props: Record<string, unknown>) => {
      const {
        whileHover,
        initial,
        animate,
        exit,
        transition,
        layout,
        variants,
        ...rest
      } = props;
      return <div {...rest} />;
    },
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
