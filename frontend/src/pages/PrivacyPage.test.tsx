import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PRIVACY_CONTACT, PrivacyPage } from "./PrivacyPage";

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

  it("says how to ask for the account to be deleted", () => {
    renderPage();

    const contact = screen.getByRole("link", { name: PRIVACY_CONTACT });
    expect(contact).toHaveAttribute("href", `mailto:${PRIVACY_CONTACT}`);
    expect(screen.getByText(/until you ask us to delete your account/)).toBeInTheDocument();
  });
});
