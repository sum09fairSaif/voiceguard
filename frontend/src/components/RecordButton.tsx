import mic from "../assets/icons/mic.svg";
import styles from "./RecordButton.module.css";

type Props = {
  recording: boolean;
  disabled?: boolean;
  onClick: () => void;
};

// The big round microphone button from the designs (Figma 1:348-1:351).
// While recording, the rings pulse and the microphone becomes a stop square.
export function RecordButton({ recording, disabled = false, onClick }: Props) {
  return (
    <div className={recording ? `${styles.outer} ${styles.listening}` : styles.outer}>
      <div className={styles.middle}>
        <button
          type="button"
          className={styles.button}
          onClick={onClick}
          disabled={disabled}
          aria-label={recording ? "Stop recording" : "Start recording"}
          aria-pressed={recording}
        >
          {recording ? (
            <span className={styles.stop} />
          ) : (
            <img src={mic} alt="" width={20.55} height={29.55} />
          )}
        </button>
      </div>
    </div>
  );
}
