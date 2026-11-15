import { PageHeading } from "../../components/PageHeading";
import styles from "../AccountPage.module.css";

// Shown when this session can't record a Voice ID: only the signup session
// may (or, briefly, accounts made before that rule). Until account recovery
// exists (#20), the way forward is the VoiceGuard team. Signing out is in the
// header, as on every signed-in screen.
export function EnrollClosed() {
  return (
    <div className={styles.heading}>
      <PageHeading
        eyebrow="Voice ID"
        title="Voice ID can’t be set up here."
        subtitle="To keep your account safe, a Voice ID can only be set up right after creating the account. Please contact the VoiceGuard team to set it up."
      />
    </div>
  );
}
