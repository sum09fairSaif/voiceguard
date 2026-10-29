import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EnrollIntro } from "./EnrollIntro";

describe("EnrollIntro", () => {
  it("shows the Figma heading, step 1 of 3 and the three promises", () => {
    render(<EnrollIntro onStart={() => {}} />);

    expect(screen.getByRole("heading", { name: "Meet your new key." })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("Speak, don’t remember")).toBeInTheDocument();
    expect(screen.getByText("Your voiceprint is stored encrypted.")).toBeInTheDocument();
    expect(screen.getByText("Built for peace of mind")).toBeInTheDocument();
  });

  it("can't start until the user agrees to use their voice", async () => {
    const onStart = vi.fn();
    render(<EnrollIntro onStart={onStart} />);
    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: /set up my voice id/i });

    expect(screen.getByRole("checkbox", { name: /i agree to use my voice/i })).not.toBeChecked();
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onStart).not.toHaveBeenCalled();
  });

  it("starts once the box is ticked, and locks again if it's unticked", async () => {
    const onStart = vi.fn();
    render(<EnrollIntro onStart={onStart} />);
    const user = userEvent.setup();
    const checkbox = screen.getByRole("checkbox", { name: /i agree to use my voice/i });
    const button = screen.getByRole("button", { name: /set up my voice id/i });

    await user.click(checkbox);
    expect(button).toBeEnabled();
    await user.click(button);
    expect(onStart).toHaveBeenCalledTimes(1);

    await user.click(checkbox);
    expect(button).toBeDisabled();
  });

  it("ticks the box from its text too, since the whole line is the label", async () => {
    render(<EnrollIntro onStart={() => {}} />);
    await userEvent.setup().click(screen.getByText(/i agree to use my voice/i));
    expect(screen.getByRole("checkbox", { name: /i agree to use my voice/i })).toBeChecked();
  });
});
