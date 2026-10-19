import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";

// Stands in for the passage screen until #13 (Show a challenge passage to read).
export function VerifyPlaceholderPage() {
  return (
    <Page>
      <Logo />
      <PageHeading
        eyebrow="Secure sign in"
        title="You’re all set."
        subtitle="Your account is ready. Next, you’ll read a short passage aloud."
      />
    </Page>
  );
}
