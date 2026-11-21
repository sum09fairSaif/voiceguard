import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { describeLoginError, logIn } from "../api/auth";
import { getEnrollment } from "../api/enroll";
import { invalidFields } from "../api/errors";
import { clearToken, saveToken } from "../api/session";
import posthog, { isPostHogConfigured } from "../posthog";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TextField } from "../components/TextField";
import type { SignOutState } from "../hooks/useSignOut";
import { useStillShown } from "../hooks/useStillShown";
import type { ConfirmEmailState } from "./ConfirmEmailPage";
import type { ForgotPasswordState } from "./ForgotPasswordPage";
import type { PasswordChangedState } from "./ResetPasswordPage";
import styles from "./SignInPage.module.css";
import { validateSignIn, type SignInErrors, type SignInForm } from "./signInValidation";

// Figma 19:97 "Sign in". The "Sign in with Voice ID" button is left out for now:
// a voice check needs a token, which needs the password first.
export function SignInPage() {
  const navigate = useNavigate();
  const arrivedWith = useLocation().state as (SignOutState & Partial<PasswordChangedState>) | null;
  const serverSignOutFailed = arrivedWith?.serverSignOutFailed === true;
  const passwordChanged = arrivedWith?.passwordChanged === true;
  const [form, setForm] = useState<SignInForm>({ email: "", password: "" });
  const [errors, setErrors] = useState<SignInErrors>({});
  const [formError, setFormError] = useState("");
  const [offerConfirm, setOfferConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const shown = useStillShown();

  function update(field: keyof SignInForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const found = validateSignIn(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const result = await logIn({ email: form.email.trim(), password: form.password });
      // The user may have gone to Create account while this was running.
      if (!shown.current) return;
      saveToken(result.access_token, result.user);
      if (isPostHogConfigured) posthog.capture("signed_in");
      // People without a Voice ID set one up first (#10). If the status can't
      // be read, the enrollment page explains, retries, and shows enrolled
      // users the way on.
      let destination = "/enroll";
      try {
        const enrollment = await getEnrollment();
        if (enrollment.status === "enrolled") destination = "/verify";
      } catch {
        // Handled on the enrollment page.
      }
      if (!shown.current) {
        clearToken();
        return;
      }
      navigate(destination, { replace: true });
    } catch (error) {
      if (!shown.current) return;
      const rejected = invalidFields(error);
      const fieldErrors: SignInErrors = {};
      for (const name of rejected) {
        if (name === "email" || name === "password") fieldErrors[name] = "Check this field and try again.";
      }
      setErrors(fieldErrors);
      // Wrong credentials and lockouts are about the whole form, never one
      // field, so they don't hint at which part was wrong.
      setFormError(describeLoginError(error));
      // An account that never confirmed its email is answered exactly like a
      // wrong password, and locked the same way (#111). So the way back to
      // confirming comes with every such answer: it gives nothing away.
      setOfferConfirm(isAxiosError(error) && (error.response?.status === 401 || error.response?.status === 423));
      setSubmitting(false);
    }
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          eyebrow="Good to have you back"
          title="Welcome back."
          subtitle="Sign in to your own little corner of peace of mind."
        />
      </div>

      {serverSignOutFailed && (
        <p className={styles.notice} role="status">
          You're signed out on this device, but we couldn't reach VoiceGuard to end your session everywhere. It ends
          on its own within 75 minutes.
        </p>
      )}

      {passwordChanged && (
        <p className={styles.notice} role="status">
          Your password has been changed, and your account has been signed out on every device. Sign in with your new
          password.
        </p>
      )}

      {/* Fields lock while sending, so a server error always matches what was sent. */}
      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <TextField
          id="email"
          label="Email address"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          value={form.email}
          onChange={(event) => update("email", event.target.value)}
          error={errors.email}
          disabled={submitting}
        />
        <TextField
          id="password"
          label="Password"
          type="password"
          placeholder="Your password"
          autoComplete="current-password"
          value={form.password}
          onChange={(event) => update("password", event.target.value)}
          error={errors.password}
          disabled={submitting}
        />
        {/* Carries over the email, if one was typed, so it needn't be typed twice. */}
        <Link
          to="/forgot-password"
          state={{ email: form.email.trim() } satisfies ForgotPasswordState}
          className={styles.forgot}
        >
          Forgot password?
        </Link>

        {formError && (
          <p className={styles.formError} role="alert">
            {formError}
          </p>
        )}
        {formError && offerConfirm && (
          <p className={styles.confirmHint}>
            Signed up but haven’t confirmed your email yet?{" "}
            <Link to="/confirm-email" state={{ email: form.email.trim() } satisfies ConfirmEmailState}>
              Enter your code
            </Link>
          </p>
        )}

        <div className={styles.submit}>
          <Button type="submit" showArrow={!submitting} disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in securely"}
          </Button>
        </div>
      </form>

      <p className={styles.switch}>
        New to VoiceGuard? <Link to="/signup">Create account</Link>
      </p>
    </Page>
  );
}
