import { isAxiosError } from "axios";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { isWellFormedCode, normalizeCode } from "../api/emailVerification";
import { describeApiError } from "../api/errors";
import { confirmRecoveryCode, requestRecoveryCode } from "../api/recovery";
import { endSession } from "../api/session";
import badgeLock from "../assets/icons/badge-lock.svg";
import { Button } from "../components/Button";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { ProtectedNote } from "../components/ProtectedNote";
import { SignedInHeader } from "../components/SignedInHeader";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import styles from "./ConfirmEmailPage.module.css";

// What the Voice ID screens read to know a new recording replaces the old one.
export type RecoveringState = { recovering?: boolean };

const BADGE = { src: badgeLock, width: 15.7, height: 19.7 };

export const CODE_SENT = "We’ve sent a 6-digit code to your email address. It replaces any earlier one.";
export const CODE_FORMAT = "Enter the 6-digit code from the email.";
export const CODE_NOT_ACCEPTED =
  "That code didn’t work. It may be mistyped, used up or expired. Check the email, or send a new code.";
export const NOT_PAUSED =
  "You can record a new Voice ID once voice checks are paused after failed tries. Try the voice check first.";
export const NOT_CONFIRMED = "Please confirm your email address first.";

// No Figma frame of its own: built from the confirm-email screen's parts.
//
// Offered once voice checks are paused after failed tries (#20). The code
// proves the inbox; with the password this session already has, it lets the
// person record a new Voice ID. It never opens the account: afterwards they
// sign in again and pass a voice check with the new voice.
export function RecoverPage() {
  const navigate = useNavigate();
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"" | "sending" | "confirming">("");
  const shown = useStillShown();

  function handleError(error: unknown, overrides: Partial<Record<number, string>>) {
    if (isAxiosError(error) && error.response?.status === 401) {
      endSession();
      navigate("/signin", { replace: true });
      return;
    }
    setFormError(describeApiError(error, { 403: NOT_CONFIRMED, 409: NOT_PAUSED, ...overrides }));
  }

  async function sendCode() {
    setFormError("");
    setNotice("");
    setBusy("sending");
    try {
      await requestRecoveryCode();
      if (!shown.current) return;
      setSent(true);
      setCode("");
      setCodeError("");
      setNotice(CODE_SENT);
    } catch (error) {
      if (!shown.current) return;
      handleError(error, {});
    }
    setBusy("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setNotice("");
    const cleaned = normalizeCode(code);
    if (!isWellFormedCode(cleaned)) {
      setCodeError(CODE_FORMAT);
      return;
    }
    setBusy("confirming");
    try {
      await confirmRecoveryCode(cleaned);
      if (!shown.current) return;
      const state: RecoveringState = { recovering: true };
      navigate("/enroll", { replace: true, state });
    } catch (error) {
      if (!shown.current) return;
      handleError(error, { 400: CODE_NOT_ACCEPTED, 422: CODE_FORMAT });
      setBusy("");
    }
  }

  return (
    <Page>
      <SignedInHeader />
      <div className={styles.heading}>
        <PageHeading
          badgeIcon={BADGE}
          eyebrow="Voice ID"
          title="Record a new Voice ID."
          subtitle={
            sent
              ? "Enter the 6-digit code from the email. Then you’ll record three short sentences, as when you set it up."
              : "If the voice check keeps failing, you can record your Voice ID again. First we’ll email you a code, to make sure it’s you."
          }
        />
      </div>

      {sent ? (
        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <TextField
            id="code"
            label="Code from the email"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            maxLength={20}
            value={code}
            onChange={(event) => {
              setCode(event.target.value);
              setCodeError("");
            }}
            error={codeError}
            disabled={busy !== ""}
          />

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}
          {notice && (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          )}

          <div className={styles.submit}>
            <Button type="submit" showArrow={busy !== "confirming"} disabled={busy !== ""}>
              {busy === "confirming" ? "Checking…" : "Continue"}
            </Button>
          </div>
        </form>
      ) : (
        <div className={styles.form}>
          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}
          <div className={styles.submit}>
            <Button type="button" showArrow={busy !== "sending"} disabled={busy !== ""} onClick={sendCode}>
              {busy === "sending" ? "Sending…" : "Email me a code"}
            </Button>
          </div>
        </div>
      )}

      {sent && (
        <button type="button" className={styles.link} onClick={sendCode} disabled={busy !== ""}>
          {busy === "sending" ? "Sending…" : "Send a new code"}
        </button>
      )}
      <Link to="/verify" className={styles.secondaryLink}>
        Back to the voice check
      </Link>

      <ProtectedNote>Your current Voice ID keeps working until the new one is complete</ProtectedNote>
    </Page>
  );
}
