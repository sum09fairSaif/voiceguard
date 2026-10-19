import type { ButtonHTMLAttributes } from "react";
import arrowRight from "../assets/icons/arrow-right.svg";
import styles from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  showArrow?: boolean;
};

export function Button({ showArrow = false, children, ...buttonProps }: Props) {
  return (
    <button className={styles.button} {...buttonProps}>
      {children}
      {showArrow && (
        <img className={styles.arrow} src={arrowRight} alt="" width={12.4292} height={9.2625} />
      )}
    </button>
  );
}
