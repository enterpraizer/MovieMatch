import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { StarRating } from "./StarRating";
import { useRatingsStore } from "@/store/ratings-store";

describe("StarRating", () => {
  beforeEach(() => {
    useRatingsStore.setState({ ratings: {} });
  });

  it("renders 5 star zones", () => {
    render(<StarRating movieId={1} movieTitle="Test" />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByLabelText(`${i} stars`)).toBeInTheDocument();
    }
  });

  it("clicking 3rd star right-half sets score to 3", () => {
    render(<StarRating movieId={10} movieTitle="Test" />);
    fireEvent.click(screen.getByLabelText("3 stars"));
    expect(useRatingsStore.getState().ratings[10]).toBe(3);
  });

  it("clicking 3rd star left-half sets score to 2.5", () => {
    render(<StarRating movieId={11} movieTitle="Test" />);
    fireEvent.click(screen.getByLabelText("2.5 stars"));
    expect(useRatingsStore.getState().ratings[11]).toBe(2.5);
  });

  it("shows filled stars up to current rating", () => {
    useRatingsStore.setState({ ratings: { 20: 4 } });
    const { container } = render(<StarRating movieId={20} movieTitle="Test" />);
    const filledStars = container.querySelectorAll(
      'svg[class*="fill-"]'
    );
    expect(filledStars.length).toBeGreaterThanOrEqual(4);
  });

  it("has data-star attributes on elements", () => {
    const { container } = render(<StarRating movieId={1} movieTitle="Test" />);
    for (let i = 1; i <= 5; i++) {
      expect(container.querySelector(`[data-star="${i}"]`)).toBeInTheDocument();
    }
  });
});
