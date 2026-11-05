import type { ButtonHTMLAttributes } from "react";
import arrowRight from "../assets/icons/arrow-right.svg";
import styles from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  showArrow?: boolean;
  variant?: "primary" | "secondary";
};

export function Button({ showArrow = false, variant = "primary", children, ...buttonProps }: Props) {
  return (
    <button className={`${styles.button} ${styles[variant]}`} {...buttonProps}>
      {children}
      {showArrow && (
        <img className={styles.arrow} src={arrowRight} alt="" width={12.4292} height={9.2625} />
      )}
    </button>
  );
}
