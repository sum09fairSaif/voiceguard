import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { confirmEmail, isWellFormedCode, normalizeCode, sendEmailCode } from "../api/emailVerification";
import { describeApiError } from "../api/errors";
import { startSession } from "../api/session";
import badgeLock from "../assets/icons/badge-lock.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { ProtectedNote } from "../components/ProtectedNote";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import { track } from "../posthog";
import styles from "./ConfirmEmailPage.module.css";
import { EMAIL_PATTERN } from "./signupValidation";

// Signup passes on the address it used; there's no session yet.
export type ConfirmEmailState = { email?: string };

const BADGE = { src: badgeLock, width: 15.7, height: 19.7 };

export const EMAIL_FORMAT = "Enter the email address you signed up with.";
export const CODE_FORMAT = "Enter the 6-digit code from the email.";
export const CODE_NOT_ACCEPTED =
  "That code didn’t work. It may be mistyped, used up or expired. Check the email, or send a new code.";
export const NEW_CODE_SENT = "If the address can be used, we’ve sent it a new code. It replaces any earlier one.";

// No Figma frame of its own: built from the parts of "Reset password"
// (19:146), the other one-field screen about an email.
//
// Signup comes here while email confirmation is on (#110). It looks the
// same whether or not the address already has an account (#111): a new
// address has been sent a code, one with an account a note telling its owner
// to sign in. Entering the code confirms the address and signs in.
export function ConfirmEmailPage() {
  const navigate = useNavigate();
  const passedEmail = (useLocation().state as ConfirmEmailState | null)?.email ?? "";
  // Without one (say, after a refresh), the screen asks for the address too.
  const askForEmail = passedEmail === "";
  const [email, setEmail] = useState(passedEmail);
  const [emailError, setEmailError] = useState("");
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"" | "confirming" | "sending">("");
  const shown = useStillShown();

  // The address to use, or "" after showing why it can't be used.
  function checkedEmail(): string {
    const trimmed = email.trim();
    if (!EMAIL_PATTERN.test(trimmed)) {
      setEmailError(EMAIL_FORMAT);
      return "";
    }
    return trimmed;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setNotice("");
    const address = checkedEmail();
    const cleaned = normalizeCode(code);
    if (!isWellFormedCode(cleaned)) setCodeError(CODE_FORMAT);
    if (!address || !isWellFormedCode(cleaned)) return;

    setBusy("confirming");
    try {
      const result = await confirmEmail(address, cleaned);
      if (!shown.current) return;
      // The session starts here, as after signing in.
      startSession(result.user);
      track("account_created");
      // A new account has no Voice ID yet, so set one up first (#10).
      navigate("/enroll", { replace: true });
    } catch (error) {
      if (!shown.current) return;
      setFormError(describeApiError(error, { 400: CODE_NOT_ACCEPTED, 422: CODE_FORMAT }));
      setBusy("");
    }
  }

  async function sendAgain() {
    setFormError("");
    setNotice("");
    const address = checkedEmail();
    if (!address) return;

    setBusy("sending");
    try {
      await sendEmailCode(address);
      if (!shown.current) return;
      setCode("");
      setCodeError("");
      setNotice(NEW_CODE_SENT);
    } catch (error) {
      if (!shown.current) return;
      setFormError(describeApiError(error));
    }
    setBusy("");
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
            askForEmail
              ? "Enter your email address and the 6-digit code we sent to it, to confirm the address is yours."
              : `We’ve sent an email to ${passedEmail}. Enter the 6-digit code from it to confirm the address is yours.`
          }
        />
      </div>

      {/* Fields lock while sending, so an error always matches what was sent. */}
      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        {askForEmail && (
          <TextField
            id="email"
            label="Email address"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setEmailError("");
            }}
            error={emailError}
            disabled={busy !== ""}
          />
        )}
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
      {/* Signing up again with the right address starts over; an unconfirmed
          account doesn't hold on to the address. */}
      <Link to="/signup" replace className={styles.secondaryLink}>
        Wrong address? Sign up again
      </Link>

      <ProtectedNote>Only someone with access to this inbox can confirm it</ProtectedNote>
    </Page>
  );
}
