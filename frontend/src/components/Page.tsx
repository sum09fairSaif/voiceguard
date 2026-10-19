import type { ReactNode } from "react";
import styles from "./Page.module.css";

// The designs are mobile screens, so every page is a phone-width column,
// centred when the window is wider.
export function Page({ children }: { children: ReactNode }) {
  return (
    <div className={styles.viewport}>
      <main className={styles.column}>{children}</main>
    </div>
  );
}
