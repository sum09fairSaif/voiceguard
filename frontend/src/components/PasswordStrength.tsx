import { passwordStrength } from "../pages/signupValidation";
import styles from "./PasswordStrength.module.css";

// Three bars and a word under the password field: a guide while typing. The
// server's check (including breached passwords) is what decides.
export function PasswordStrength({ password }: { password: string }) {
  const { level, label } = passwordStrength(password);
  if (!password) return null;
  return (
    <div className={styles.strength}>
      <div className={styles.bars} aria-hidden="true">
        {[1, 2, 3].map((bar) => (
          <span key={bar} className={`${styles.bar} ${bar <= level ? styles[`level${level}`] : ""}`} />
        ))}
      </div>
      <p className={styles.label} aria-live="polite">
        Password strength: {label}
      </p>
    </div>
  );
}
