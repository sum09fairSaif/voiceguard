import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { describeLoginError, logIn } from "../api/auth";
import { getEnrollment } from "../api/enroll";
import { invalidFields } from "../api/errors";
import { saveToken } from "../api/session";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TextField } from "../components/TextField";
import styles from "./SignInPage.module.css";
import { validateSignIn, type SignInErrors, type SignInForm } from "./signInValidation";

// Figma 1:95 "Sign in". The "Sign in with Voice ID" button is left out for now:
// a voice check needs a token, which needs the password first.
export function SignInPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<SignInForm>({ email: "", password: "" });
  const [errors, setErrors] = useState<SignInErrors>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
      saveToken(result.access_token);
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
      navigate(destination, { replace: true });
    } catch (error) {
      const rejected = invalidFields(error);
      const fieldErrors: SignInErrors = {};
      for (const name of rejected) {
        if (name === "email" || name === "password") fieldErrors[name] = "Check this field and try again.";
      }
      setErrors(fieldErrors);
      // Wrong credentials and lockouts are about the whole form, never one
      // field, so they don't hint at which part was wrong.
      setFormError(describeLoginError(error));
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
        {/* Placeholder until password recovery exists; it does nothing yet. */}
        <button type="button" className={styles.forgot}>
          Forgot password?
        </button>

        {formError && (
          <p className={styles.formError} role="alert">
            {formError}
          </p>
        )}

        <div className={styles.submit}>
          <Button type="submit" showArrow={!submitting} disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in securely"}
          </Button>
        </div>
      </form>

      <p className={styles.switch}>
        <Link to="/signup">New to VoiceGuard? Create account</Link>
      </p>
    </Page>
  );
}
