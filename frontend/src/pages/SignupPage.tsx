import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "../api/auth";
import { describeApiError, invalidFields } from "../api/errors";
import { saveToken } from "../api/session";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TextField } from "../components/TextField";
import { useStillShown } from "../hooks/useStillShown";
import styles from "./SignupPage.module.css";
import { validateSignup, type SignupErrors, type SignupForm } from "./signupValidation";

const DUPLICATE_EMAIL = "An account with this email already exists.";

// Backend field names (from a 422) mapped to the form's own names.
const SERVER_FIELDS: Record<string, keyof SignupForm> = {
  full_name: "fullName",
  email: "email",
  password: "password",
};

export function SignupPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<SignupForm>({ fullName: "", email: "", password: "" });
  const [errors, setErrors] = useState<SignupErrors>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const shown = useStillShown();

  function update(field: keyof SignupForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const found = validateSignup(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const result = await signup({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      // The user may have gone to Sign in while this was running.
      if (!shown.current) return;
      saveToken(result.access_token);
      // A new account has no Voice ID yet, so set one up first (#10).
      navigate("/enroll", { replace: true });
    } catch (error) {
      if (!shown.current) return;
      const rejected = invalidFields(error);
      if (rejected.length > 0) {
        const fieldErrors: SignupErrors = {};
        for (const name of rejected) {
          const field = SERVER_FIELDS[name];
          if (field) fieldErrors[field] = "Check this field and try again.";
        }
        setErrors(fieldErrors);
      }
      const message = describeApiError(error, { 409: DUPLICATE_EMAIL });
      if (message === DUPLICATE_EMAIL) {
        setErrors({ email: DUPLICATE_EMAIL });
      } else {
        setFormError(message);
      }
      setSubmitting(false);
    }
  }

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          eyebrow="Let’s get to know you"
          title="Your security starts here."
          subtitle="Create an account. Take the first step toward a safer digital life."
        />
      </div>

      {/* Fields lock while sending, so a server error always matches what was sent. */}
      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <TextField
          id="full-name"
          label="Full name"
          placeholder="Alex Morgan"
          autoComplete="name"
          value={form.fullName}
          onChange={(event) => update("fullName", event.target.value)}
          error={errors.fullName}
          disabled={submitting}
        />
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
          placeholder="At least 8 characters"
          autoComplete="new-password"
          value={form.password}
          onChange={(event) => update("password", event.target.value)}
          error={errors.password}
          disabled={submitting}
        />

        {formError && (
          <p className={styles.formError} role="alert">
            {formError}
          </p>
        )}

        <div className={styles.submit}>
          <Button type="submit" showArrow={!submitting} disabled={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </Button>
        </div>
      </form>

      <p className={styles.switch}>
        <Link to="/signin">Already a member? Sign in</Link>
      </p>
      <p className={styles.terms}>By continuing, you agree to our Terms &amp; Privacy Policy.</p>
    </Page>
  );
}
