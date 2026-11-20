import type { ReactNode } from "react";
import noteLock from "../assets/icons/note-lock.svg";
import styles from "./ProtectedNote.module.css";

// Figma 19:146: the grey card with a padlock at the foot of the password
// reset screens.
export function ProtectedNote({ children }: { children: ReactNode }) {
  return (
    <p className={styles.note}>
      <img src={noteLock} alt="" width={14.3917} height={18.0583} />
      <span className={styles.text}>{children}</span>
    </p>
  );
}
