export type SignupForm = {
  fullName: string;
  email: string;
  password: string;
};

export type SignupErrors = Partial<Record<keyof SignupForm, string>>;

// Same rules as the backend (backend/schemas.py), so most mistakes are caught
// before anything is sent.
const MAX_NAME_LENGTH = 100;
const MIN_PASSWORD_LENGTH = 8;
// bcrypt only reads the first 72 bytes of a password.
const MAX_PASSWORD_BYTES = 72;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateSignup(form: SignupForm): SignupErrors {
  const errors: SignupErrors = {};
  const name = form.fullName.trim();
  if (!name) {
    errors.fullName = "Enter your full name.";
  } else if (name.length > MAX_NAME_LENGTH) {
    errors.fullName = `Full name must be ${MAX_NAME_LENGTH} characters or fewer.`;
  }
  if (!EMAIL_PATTERN.test(form.email.trim())) {
    errors.email = "Enter a valid email address.";
  }
  if (form.password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  } else if (new TextEncoder().encode(form.password).length > MAX_PASSWORD_BYTES) {
    errors.password = "That password is too long. Try a shorter one.";
  }
  return errors;
}
