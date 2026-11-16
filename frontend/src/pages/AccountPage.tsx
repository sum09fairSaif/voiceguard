import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeApiError } from "../api/errors";
import { getMe, type Me } from "../api/me";
import { clearToken } from "../api/session";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { useSignOut } from "../hooks/useSignOut";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import styles from "./AccountPage.module.css";

const DAY = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const MOMENT = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? "";
}

// The home screen after a full sign-in (password and an approved voice
// check). The server decides who may see it: it answers 403 to a password
// alone and 401 to a missing or expired session, and this page follows that.
export function AccountPage() {
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  // React's development mode mounts screens twice.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    getMe()
      .then(setMe)
      .catch((err) => {
        const status = isAxiosError(err) ? err.response?.status : undefined;
        if (status === 401) {
          clearToken();
          navigate("/signin", { replace: true });
        } else if (status === 403) {
          // Signed in with a password, but the voice check isn't done.
          navigate("/verify", { replace: true });
        } else {
          setError(describeApiError(err));
        }
      });
  }, [navigate]);

  const signOut = useSignOut();

  function handleSignOut() {
    void signOut();
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          eyebrow="Your account"
          title={me ? `Welcome back, ${firstName(me.full_name)}.` : "Your account"}
          subtitle="Signed in with your password and your voice."
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
          <dl className={styles.details} aria-label="Account details">
            <div className={styles.row}>
              <dt>Email</dt>
              <dd>{me.email}</dd>
            </div>
            <div className={styles.row}>
              <dt>Member since</dt>
              <dd>{DAY.format(new Date(me.created_at))}</dd>
            </div>
            <div className={styles.row}>
              <dt>Voice ID</dt>
              <dd>{me.enrolled_at ? `Set up ${DAY.format(new Date(me.enrolled_at))}` : "Not set up"}</dd>
            </div>
            <div className={styles.row}>
              <dt>Last sign-in</dt>
              <dd>{me.previous_sign_in_at ? MOMENT.format(new Date(me.previous_sign_in_at)) : "This is your first"}</dd>
            </div>
          </dl>
          <p className={styles.note}>Don’t recognise your last sign-in? Sign out and tell the VoiceGuard team.</p>
        </>
      )}

      <div className={styles.action}>
        <Button type="button" variant="secondary" onClick={handleSignOut}>
          Sign out
        </Button>
      </div>
    </Page>
  );
}
