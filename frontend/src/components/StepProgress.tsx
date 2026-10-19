import styles from "./StepProgress.module.css";

type Props = {
  current: number;
  total: number;
};

// The segmented bar at the top of the voice screens: one segment per step,
// filled up to and including the current one.
export function StepProgress({ current, total }: Props) {
  return (
    <div
      className={styles.track}
      role="progressbar"
      aria-label="Progress"
      aria-valuemin={1}
      aria-valuemax={total}
      aria-valuenow={current}
    >
      {Array.from({ length: total }, (_, index) => (
        <span key={index} className={index < current ? styles.done : styles.todo} />
      ))}
    </div>
  );
}
