import { Link } from "react-router-dom";
import cardShield from "../assets/icons/home-card-shield.svg";
import rowMic from "../assets/icons/row-mic.svg";
import rowPulse from "../assets/icons/row-pulse.svg";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TabBar } from "../components/TabBar";
import { useMe } from "../hooks/useMe";
import styles from "./AccountPage.module.css";

const MOMENT = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? "";
}

// Home, after a full sign-in (password and an approved voice check), from
// Figma 19:413. The design's "Recent activity" row shows the last sign-in
// instead until there's an Activity screen, and the "All systems ready" label
// is left out: nothing here checks that.
export function AccountPage() {
  const { me, error } = useMe();
  const enrolled = Boolean(me?.enrolled_at);

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Your protected space"
          title={me ? `Hello, ${firstName(me.full_name)}.` : "Hello."}
          subtitle="A little more confidence for your everyday."
        />
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {!me && !error && <p className={styles.status}>Loading your account…</p>}

      {me && (
        <>
          <section className={styles.card} aria-labelledby="home-card-title">
            <div className={styles.cardTop}>
              <img src={cardShield} alt="" width={23.6} height={26.27} />
              {enrolled && (
                <span className={styles.badge}>
                  <span aria-hidden="true">●</span> Protected
                </span>
              )}
            </div>
            <h2 id="home-card-title" className={styles.cardTitle}>
              Your voice.
              <br />
              Your peace of mind.
            </h2>
            <p className={styles.cardText}>
              {enrolled
                ? "Voice ID is active and ready when you need it."
                : "Set up your Voice ID to protect your account with your voice."}
            </p>
            <Link to={enrolled ? "/verify" : "/enroll"} className={styles.cardLink}>
              {enrolled ? "Try a voice check" : "Set up Voice ID"} <span aria-hidden="true">→</span>
            </Link>
          </section>

          <section className={styles.security} aria-labelledby="home-security">
            <h2 id="home-security" className={styles.sectionTitle}>
              Your security
            </h2>
            <ul className={styles.rows}>
              <li className={styles.row}>
                <span className={styles.rowIcon}>
                  <img src={rowMic} alt="" width={13.13} height={18.88} />
                </span>
                <span className={styles.rowText}>
                  <span className={styles.rowTitle}>My Voice ID</span>
                  <span className={styles.rowDetail}>{enrolled ? "Enrolled & encrypted" : "Not set up"}</span>
                </span>
              </li>
              <li className={styles.row}>
                <span className={styles.rowIcon}>
                  <img src={rowPulse} alt="" width={18.88} height={15.05} />
                </span>
                <span className={styles.rowText}>
                  <span className={styles.rowTitle}>Last sign-in</span>
                  <span className={styles.rowDetail}>
                    {me.previous_sign_in_at
                      ? MOMENT.format(new Date(me.previous_sign_in_at))
                      : "This is your first"}
                  </span>
                </span>
              </li>
            </ul>
            <p className={styles.note}>Don’t recognise your last sign-in? Sign out and tell the VoiceGuard team.</p>
          </section>
        </>
      )}

      <TabBar />
    </Page>
  );
}
