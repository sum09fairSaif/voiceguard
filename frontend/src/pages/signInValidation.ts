import { EMAIL_PATTERN } from "./signupValidation";

export type SignInForm = {
  email: string;
  password: string;
};

export type SignInErrors = Partial<Record<keyof SignInForm, string>>;

// Only "is it filled in" checks: the signup password rules don't apply here,
// and a wrong password of any length gets the same answer from the server.
export function validateSignIn(form: SignInForm): SignInErrors {
  const errors: SignInErrors = {};
  if (!EMAIL_PATTERN.test(form.email.trim())) {
    errors.email = "Enter a valid email address.";
  }
  if (!form.password) {
    errors.password = "Enter your password.";
  }
  return errors;
}
