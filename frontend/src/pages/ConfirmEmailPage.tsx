import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { confirmEmail, isWellFormedCode, normalizeCode, sendEmailCode } from "../api/emailVerification";
import { describeApiError, MESSAGES } from "../api/errors";
import { clearToken, getSignedInUser, getToken, saveToken } from "../api/session";
import badgeLock from "../assets/icons/badge-lock.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { ProtectedNote } from "../components/ProtectedNote";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import posthog, { isPostHogConfigured } from "../posthog";
import styles from "./ConfirmEmailPage.module.css";

const BADGE = { src: badgeLock, width: 15.7, height: 19.7 };

export const CODE_FORMAT = "Enter the 6-digit code from the email.";
export const CODE_NOT_ACCEPTED =
  "That code didn’t work. It may be mistyped, used up or expired. Check the email, or send a new code.";
export const NEW_CODE_SENT = "We’ve sent a new code. It replaces any earlier one.";

// No Figma frame of its own: built from the parts of "Reset password"
// (19:146), the other one-field screen about an email. New accounts come
// here while their address is unconfirmed (#110); signup has already
// emailed the first code.
export function ConfirmEmailPage() {
  const navigate = useNavigate();
  const email = getSignedInUser()?.email;
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"" | "confirming" | "sending">("");
  const shown = useStillShown();

  // Already confirmed (409): nothing to do here, carry on to Voice ID.
  function alreadyConfirmed(error: unknown): boolean {
    return isAxiosError(error) && error.response?.status === 409;
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
      const result = await confirmEmail(cleaned);
      if (!shown.current) return;
      // Same token; the saved account now says it's confirmed.
      const token = getToken();
      if (token) saveToken(token, result.user);
      if (isPostHogConfigured) posthog.capture("email_confirmed");
      navigate("/enroll", { replace: true });
    } catch (error) {
      if (!shown.current) return;
      if (alreadyConfirmed(error)) {
        navigate("/enroll", { replace: true });
        return;
      }
      setFormError(describeApiError(error, { 400: CODE_NOT_ACCEPTED, 422: CODE_FORMAT }));
      setBusy("");
    }
  }

  async function sendAgain() {
    setFormError("");
    setNotice("");
    setBusy("sending");
    try {
      await sendEmailCode();
      if (!shown.current) return;
      setCode("");
      setCodeError("");
      setNotice(NEW_CODE_SENT);
    } catch (error) {
      if (!shown.current) return;
      if (alreadyConfirmed(error)) {
        navigate("/enroll", { replace: true });
        return;
      }
      setFormError(describeApiError(error, { 503: MESSAGES.unavailable }));
    }
    setBusy("");
  }

  // A mistyped address can't be fixed here: signing up again with the right
  // one starts over, and the unconfirmed account doesn't block anything.
  function startOver() {
    clearToken();
    navigate("/signup", { replace: true });
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          badgeIcon={BADGE}
          eyebrow="One last step"
          title="Check your email."
          subtitle={
            email
              ? `We sent a 6-digit code to ${email}. Enter it below to confirm the address is yours.`
              : "We sent a 6-digit code to your email address. Enter it below to confirm the address is yours."
          }
        />
      </div>

      {/* The field locks while sending, so an error always matches what was sent. */}
      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <TextField
          id="code"
          label="Confirmation code"
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
            {busy === "confirming" ? "Confirming…" : "Confirm email"}
          </Button>
        </div>
      </form>

      <button type="button" className={styles.link} onClick={sendAgain} disabled={busy !== ""}>
        {busy === "sending" ? "Sending…" : "Send a new code"}
      </button>
      <button type="button" className={styles.secondaryLink} onClick={startOver} disabled={busy !== ""}>
        Wrong address? Sign up again
      </button>

      <ProtectedNote>Only someone with access to this inbox can confirm it</ProtectedNote>
    </Page>
  );
}
