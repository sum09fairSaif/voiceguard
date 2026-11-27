import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PrivacyPage } from "./PrivacyPage";

// The note is a promise to users, so what it says is checked here (#170).
function renderPage() {
  render(
    <MemoryRouter>
      <PrivacyPage />
    </MemoryRouter>,
  );
}

describe("Privacy note", () => {
  it("names every service a recording is sent to", () => {
    renderPage();

    expect(screen.getByText(/sent to OpenAI for transcription/)).toBeInTheDocument();
    expect(screen.getByText(/runs on Hugging Face/)).toBeInTheDocument();
  });

  it("says security records also go to PostHog, not only that they're deleted after 30 days", () => {
    renderPage();

    expect(screen.getByText(/deleted from our database after 30 days/)).toHaveTextContent(/copy also goes to PostHog/);
  });

  it("says deleting an account isn't available yet, and gives no address that might not be read", () => {
    renderPage();

    expect(screen.getByText(/Deleting an account isn’t available yet/)).toBeInTheDocument();
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });
});
