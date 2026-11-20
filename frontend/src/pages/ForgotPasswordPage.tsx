import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { describeApiError, invalidFields } from "../api/errors";
import { requestPasswordReset } from "../api/passwordReset";
import badgeLock from "../assets/icons/badge-lock.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { ProtectedNote } from "../components/ProtectedNote";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import styles from "./PasswordReset.module.css";
import { EMAIL_PATTERN } from "./signupValidation";

// Sign-in can pass on the email already typed there.
export type ForgotPasswordState = { email?: string };

const BADGE = { src: badgeLock, width: 15.7, height: 19.7 };

// Figma 19:146 "Reset password". After sending, the form gives way to a note
// that reads the same whether or not the address has an account, as the
// server's answer does.
export function ForgotPasswordPage() {
  const passedEmail = (useLocation().state as ForgotPasswordState | null)?.email ?? "";
  const [email, setEmail] = useState(passedEmail);
  const [emailError, setEmailError] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sentTo, setSentTo] = useState("");
  const shown = useStillShown();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    setEmailError("");
    setSubmitting(true);
    try {
      await requestPasswordReset(address);
      if (!shown.current) return;
      setSentTo(address);
    } catch (error) {
      if (!shown.current) return;
      if (invalidFields(error).includes("email")) setEmailError("Enter a valid email address.");
      setFormError(describeApiError(error));
    } finally {
      if (shown.current) setSubmitting(false);
    }
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          badgeIcon={BADGE}
          eyebrow="We’ve got you"
          title="A fresh start."
          subtitle="It happens. Enter your email and we’ll help you get back into your account."
        />
      </div>

      {sentTo ? (
        <div className={styles.sent} role="status">
          <p className={styles.sentTitle}>Check your email</p>
          <p>
            If there’s an account for <strong>{sentTo}</strong>, we’ve sent it a link to reset your password. The link
            works once, for 30 minutes.
          </p>
          <p>Not there after a few minutes? Check your spam folder, or send it again.</p>
          <button type="button" className={styles.again} onClick={() => setSentTo("")}>
            Send it again
          </button>
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit} noValidate>
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
            disabled={submitting}
          />

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <div className={styles.submit}>
            <Button type="submit" showArrow={!submitting} disabled={submitting}>
              {submitting ? "Sending…" : "Send reset link"}
            </Button>
          </div>
        </form>
      )}

      <Link to="/signin" className={styles.back}>
        Back to sign in
      </Link>

      <ProtectedNote>Your account stays protected throughout the reset process</ProtectedNote>
    </Page>
  );
}
