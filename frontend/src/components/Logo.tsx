import logoMark from "../assets/icons/logo-mark.svg";
import styles from "./Logo.module.css";

export function Logo() {
  return (
    <div className={styles.logo}>
      <img src={logoMark} alt="" width={38.18} height={24.9} />
      <span className={styles.name}>VoiceGuard</span>
    </div>
  );
}
