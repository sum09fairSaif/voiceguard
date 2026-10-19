import { Logo } from "./components/Logo";
import { Page } from "./components/Page";
import { PageHeading } from "./components/PageHeading";

function App() {
  return (
    <Page>
      <Logo />
      <PageHeading
        eyebrow="Your voice. Your security."
        title="Be yourself. Stay protected."
        subtitle="Voice-biometric multi-factor authentication. Screens are on their way."
      />
    </Page>
  );
}

export default App;
