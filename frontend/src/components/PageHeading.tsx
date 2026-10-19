import shieldCheck from "../assets/icons/shield-check.svg";
import styles from "./PageHeading.module.css";

type Props = {
  eyebrow: string;
  title: string;
  subtitle: string;
  // The voice screens in the designs have no shield badge.
  showBadge?: boolean;
};

// The badge, small all-caps label, big title and grey intro line that open
// every screen in the designs.
export function PageHeading({ eyebrow, title, subtitle, showBadge = true }: Props) {
  return (
    <header className={styles.heading}>
      {showBadge && (
        <div className={styles.badge}>
          <img src={shieldCheck} alt="" width={17.7} height={19.7} />
        </div>
      )}
      <p className={styles.eyebrow}>{eyebrow}</p>
      <h1 className={styles.title}>{title}</h1>
      <p className={styles.subtitle}>{subtitle}</p>
    </header>
  );
}
