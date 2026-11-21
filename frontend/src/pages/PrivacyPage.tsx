import { Link } from "react-router-dom";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import styles from "./PrivacyPage.module.css";

// Where to ask for an account to be deleted, until the app can do it.
// Forwarded on Name.com (our domain, #193).
export const PRIVACY_CONTACT = "privacy@get-voiceguard.tech";

// The short privacy note linked from sign-up (#170): what's collected, why,
// and for how long. Keep it in step with the backend and posthog.ts.
export function PrivacyPage() {
  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          eyebrow="Privacy note"
          title="What we keep, and why."
          subtitle="VoiceGuard is a student project. We collect only what it needs to sign you in and keep your account safe."
        />
      </div>

      <section className={styles.section} aria-labelledby="privacy-account">
        <h2 id="privacy-account">Your account</h2>
        <p>
          Your name, email address and password. The password is stored only as a one-way hash, never as you typed it.
          We keep these until you ask us to delete your account. The app can’t do that yet, so email{" "}
          <a href={`mailto:${PRIVACY_CONTACT}`}>{PRIVACY_CONTACT}</a> from the address you signed up with, and we’ll
          delete it along with your voiceprint. An account whose email address is never confirmed is deleted after 24
          hours.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="privacy-voice">
        <h2 id="privacy-voice">Your voice</h2>
        <p>
          Recordings are used once, to set up your Voice ID or to run a voice check, and then deleted. We keep only an
          encrypted voiceprint. To check the words you read, the recording is sent to OpenAI for transcription. To
          make your voiceprint and check that the voice is live, it is also sent to our voice model service, which
          runs on Hugging Face.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="privacy-security">
        <h2 id="privacy-security">Security records</h2>
        <p>
          Sign-ins, lockouts and voice-check results, so we can spot and stop attacks. They hold a coded id instead of
          your account id, never your email or IP address, and are deleted from our database after 30 days. A copy
          also goes to PostHog, under the same coded id, and is kept as long as the usage information below.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="privacy-analytics">
        <h2 id="privacy-analytics">How the app is used</h2>
        <p>
          Which pages are opened, a few named steps (signing up, setting up Voice ID, voice checks) and errors in the
          app, so we can see where people get stuck. These go to PostHog, under the same coded id, and are kept for up
          to a year. No clicks, screen recordings, form contents or scores.
        </p>
        <p>
          If your browser sends Do Not Track or Global Privacy Control, none of this is collected.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="privacy-email">
        <h2 id="privacy-email">Emails</h2>
        <p>Codes and password reset links are sent through Resend. Reset links stop working after 30 minutes.</p>
      </section>

      <Link to="/signup" className={styles.back}>
        Back to sign up
      </Link>
    </Page>
  );
}
