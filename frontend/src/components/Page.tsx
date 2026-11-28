import type { ReactNode } from "react";
import styles from "./Page.module.css";

type PageProps = {
  children: ReactNode;
  // The logo row. On a tablet it runs across the top of the screen.
  header?: ReactNode;
  // The tab bar. On a tablet it runs across the bottom of the screen.
  footer?: ReactNode;
};

// Every screen. On a phone (the Figma "Mobile" frames) it's one column,
// centred when the window is a little wider. On a tablet in landscape and
// wider (the "Tablet screens" frames, #227) the screen fills the window, and
// a screen's Columns sit side by side.
export function Page({ children, header, footer }: PageProps) {
  return (
    <div className={styles.viewport}>
      <main className={styles.column}>
        {header}
        <div className={styles.body}>{children}</div>
        {footer}
      </main>
    </div>
  );
}

type ColumnsProps = {
  // The left column on a tablet: the screen's heading, and the card or
  // picture the design puts under it.
  aside: ReactNode;
  // The right column on a tablet: the form, list or recorder.
  children: ReactNode;
  // "center" lines the two columns up by their middles, as on the sign-in
  // screens; "start" lines up their tops, as on Home, Activity and Settings.
  align?: "center" | "start";
};

// On a phone the two parts just follow each other, exactly as before; the
// wrappers take no part in the layout there.
export function Columns({ aside, children, align = "center" }: ColumnsProps) {
  return (
    <div className={align === "start" ? `${styles.columns} ${styles.alignStart}` : styles.columns}>
      <div className={styles.aside}>{aside}</div>
      <div className={styles.main}>{children}</div>
    </div>
  );
}
