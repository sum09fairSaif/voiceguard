import { isAxiosError } from "axios";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { describeApiError, invalidFieldProblems } from "../api/errors";
import { checkPasswordResetLink, confirmPasswordReset, tokenFromHash } from "../api/passwordReset";
import { endSession } from "../api/session";
import { heldResetLinkToken } from "../resetLinkToken";
import badgeLock from "../assets/icons/badge-lock.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { PasswordStrength } from "../components/PasswordStrength";
import { ProtectedNote } from "../components/ProtectedNote";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import styles from "./PasswordReset.module.css";
import { PASSWORD_PROBLEMS, validatePassword } from "./signupValidation";

// Sign in reads this to say the password was changed.
export type PasswordChangedState = { passwordChanged: true };

const BADGE = { src: badgeLock, width: 15.7, height: 19.7 };

// The page the emailed link opens (/reset-password#token=…). No Figma frame
// of its own: built from the parts of Reset password (19:146) and Sign up.
export function ResetPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  // Normally already taken out of the address before anything else ran
  // (resetLinkToken.ts, so analytics never sees it). If it's still in the
  // address, it's read once here and the address tidied below.
  const [token] = useState(() => heldResetLinkToken() ?? tokenFromHash(location.hash));
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [formError, setFormError] = useState("");
  const [linkUnusable, setLinkUnusable] = useState(!token);
  // The server refused the link, on opening or saving (not just a link with
  // no token).
  const [refusedByServer, setRefusedByServer] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const shown = useStillShown();
  // React's development mode mounts screens twice.
  const checked = useRef(false);

  // Check the link as soon as the page opens, so a used, replaced or expired
  // one says so at once instead of after a new password is typed. The form
  // shows meanwhile; if the check can't get an answer, saving checks again.
  useEffect(() => {
    if (!token || checked.current) return;
    checked.current = true;
    checkPasswordResetLink(token).catch((error) => {
      if (shown.current && isAxiosError(error) && error.response?.status === 400) {
        setLinkUnusable(true);
        setRefusedByServer(true);
      }
    });
  }, [token, shown]);

  useEffect(() => {
    if (location.hash) navigate({ pathname: location.pathname, search: location.search, hash: "" }, { replace: true });
  }, [location.hash, location.pathname, location.search, navigate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const found = validatePassword(password);
    setPasswordError(found ?? "");
    if (found || !token) return;

    setSubmitting(true);
    try {
      await confirmPasswordReset(token, password);
      // The reset ended every session, this browser's included: forgotten
      // even if the person has already left this page.
      endSession();
      if (!shown.current) return;
      const state: PasswordChangedState = { passwordChanged: true };
      navigate("/signin", { replace: true, state });
    } catch (error) {
      if (!shown.current) return;
      setSubmitting(false);
      if (isAxiosError(error) && error.response?.status === 400) {
        setLinkUnusable(true);
        setRefusedByServer(true);
        return;
      }
      const refused = invalidFieldProblems(error).find((problem) => problem.field === "password");
      if (refused) {
        setPasswordError(PASSWORD_PROBLEMS[refused.type] ?? "Check this field and try again.");
        return;
      }
      setFormError(describeApiError(error));
    }
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          badgeIcon={BADGE}
          eyebrow="Almost there"
          title="A new password."
          subtitle="Choose a new password for your account. You’ll use it to sign in from now on."
        />
      </div>

      {linkUnusable ? (
        <div className={styles.sent} role="alert">
          <p className={styles.sentTitle}>This link can’t be used</p>
          <p>
            Reset links work once, for 30 minutes, and only the newest one works. <Link to="/forgot-password">Ask for a
            new link</Link>.
          </p>
          {refusedByServer && (
            // The link may have been used up by an earlier save, including
            // one whose answer never arrived (e.g. the connection dropped).
            <p>
              If you’ve already set a new password with this link, <Link to="/signin">sign in</Link> with it.
            </p>
          )}
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <TextField
            id="password"
            label="New password"
            type="password"
            placeholder="At least 15 characters"
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setPasswordError("");
            }}
            error={passwordError}
            disabled={submitting}
          />
          <PasswordStrength password={password} />

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <div className={styles.submit}>
            <Button type="submit" showArrow={!submitting} disabled={submitting}>
              {submitting ? "Saving…" : "Save new password"}
            </Button>
          </div>
        </form>
      )}

      <Link to="/signin" className={styles.back}>
        Back to sign in
      </Link>

      <ProtectedNote>Saving your new password signs your account out on every device</ProtectedNote>
    </Page>
  );
}
