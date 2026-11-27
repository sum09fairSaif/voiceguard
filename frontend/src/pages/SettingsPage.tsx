import { useState } from "react";
import { Link } from "react-router-dom";
import rowArrow from "../assets/icons/row-arrow.svg";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TabBar } from "../components/TabBar";
import { useMe } from "../hooks/useMe";
import { useSignOut } from "../hooks/useSignOut";
import styles from "./SettingsPage.module.css";

const DAY = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

// Settings, from Figma 19:545. Only what the server supports today: the
// design's "Manage Voice ID", "Voice sign in" and "Security notifications"
// come when they have something behind them. "Change password" uses the
// emailed reset link, which also signs the account out everywhere.
export function SettingsPage() {
  const { me, error } = useMe();
  const signOut = useSignOut();
  const [leaving, setLeaving] = useState(false);

  function handleSignOut() {
    setLeaving(true);
    void signOut();
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="You’re in control"
          title="Make it yours."
          subtitle="Your account. Your preferences. Your peace of mind."
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
          <section className={styles.profile} aria-label="Your account">
            <span className={styles.avatar} aria-hidden="true">
              {me.full_name.trim().charAt(0).toUpperCase()}
            </span>
            <span className={styles.profileText}>
              <span className={styles.name}>{me.full_name}</span>
              <span className={styles.email}>{me.email}</span>
            </span>
          </section>

          <section aria-labelledby="settings-security">
            <h2 id="settings-security" className={styles.sectionTitle}>
              Security
            </h2>
            <ul className={styles.rows}>
              <li className={styles.row}>
                <span>Voice ID</span>
                <span className={styles.value}>
                  {me.enrolled_at ? `Set up ${DAY.format(new Date(me.enrolled_at))}` : "Not set up"}
                </span>
              </li>
              <li className={styles.row}>
                <Link to="/forgot-password" className={styles.rowLink}>
                  <span>Change password</span>
                  <img src={rowArrow} alt="" width={11.12} height={8.29} />
                </Link>
              </li>
            </ul>
          </section>
        </>
      )}

      <button type="button" className={styles.signOut} onClick={handleSignOut} disabled={leaving}>
        {leaving ? "Signing out…" : "Sign out"}
      </button>

      <TabBar />
    </Page>
  );
}
