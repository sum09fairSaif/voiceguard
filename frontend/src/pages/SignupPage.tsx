import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";

export function SignupPage() {
  return (
    <Page>
      <Logo />
      <PageHeading
        eyebrow="Let’s get to know you"
        title="Your security starts here."
        subtitle="Create an account. Take the first step toward a safer digital life."
      />
    </Page>
  );
}
