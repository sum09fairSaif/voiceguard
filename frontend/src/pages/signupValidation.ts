export type SignupForm = {
  fullName: string;
  email: string;
  password: string;
};

export type SignupErrors = Partial<Record<keyof SignupForm, string>>;

// Same rules as the backend (backend/schemas.py), so most mistakes are caught
// before anything is sent.
const MAX_NAME_LENGTH = 100;
// NIST SP 800-63B-4: at least 15 characters, and no rules about which kinds
// of character a password must contain.
export const MIN_PASSWORD_LENGTH = 15;
// bcrypt only reads the first 72 bytes of a password.
const MAX_PASSWORD_BYTES = 72;
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
  const passwordError = validatePassword(form.password);
  if (passwordError) errors.password = passwordError;
  return errors;
}

// The length rules for a new password, at signup or after a reset.
export function validatePassword(password: string): string | undefined {
  if (password.length < MIN_PASSWORD_LENGTH) return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES) {
    return "That password is too long. Try a shorter one.";
  }
  return undefined;
}

// Why the server refused a password (backend/schemas.py PASSWORD_PROBLEMS),
// in our own words. NIST asks that people are told why.
export const PASSWORD_PROBLEMS: Record<string, string> = {
  password_common: "That password is too common or has appeared in a data breach. Try a few unrelated words together.",
  password_personal: "That password is too close to your email or to VoiceGuard. Choose something unrelated.",
  password_repetitive: "That password repeats the same characters or words. Try something less predictable.",
  password_sequential: "That password is a simple sequence, like letters or keys in order. Try something less predictable.",
  string_too_short: `Use at least ${MIN_PASSWORD_LENGTH} characters.`,
};

export type Strength = { level: 0 | 1 | 2 | 3; label: string };

const RUNS = ["abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm"];

function looksPredictable(password: string): boolean {
  const lowered = password.toLowerCase();
  if (/^(.+?)\1+$/s.test(lowered)) return true;
  const core = lowered.replace(/[^a-z0-9]/g, "");
  return core.length >= 6 && RUNS.some((run) => run.repeat(4).includes(core) || [...run.repeat(4)].reverse().join("").includes(core));
}

// A rough guide while typing. The server makes the real check (including
// its list of breached passwords), so this never decides on its own.
export function passwordStrength(password: string): Strength {
  if (!password) return { level: 0, label: "" };
  if (password.length < MIN_PASSWORD_LENGTH) {
    return { level: 0, label: `${MIN_PASSWORD_LENGTH - password.length} more characters` };
  }
  if (looksPredictable(password)) return { level: 1, label: "Too predictable" };
  const varied = new Set(password.toLowerCase()).size >= 8;
  if (password.length >= 20 && varied) return { level: 3, label: "Strong" };
  return { level: varied ? 2 : 1, label: varied ? "Good" : "Too predictable" };
}
