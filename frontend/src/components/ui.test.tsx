import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, Progress, pct, timeAgo, trendLabel, trendTone } from "./ui";

describe("ui helpers", () => {
  it("formats percentages and handles missing values", () => {
    expect(pct(0.756)).toBe("76%");
    expect(pct(null)).toBe("–");
  });
  it("maps trends to labels and tones", () => {
    expect(trendLabel("needs_attention")).toBe("Needs attention");
    expect(trendTone("improving")).toBe("green");
    expect(trendTone("needs_attention")).toBe("red");
  });
  it("renders relative time", () => {
    expect(timeAgo(new Date().toISOString())).toBe("just now");
    expect(timeAgo(null)).toBe("");
  });
  it("renders badge and progress", () => {
    render(
      <div>
        <Badge tone="green">Grounded</Badge>
        <Progress value={0.5} />
      </div>,
    );
    expect(screen.getByText("Grounded")).toBeInTheDocument();
  });
});
