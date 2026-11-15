import { useState } from "react";
import { useSignOut } from "../hooks/useSignOut";
import { Logo } from "./Logo";
import styles from "./SignedInHeader.module.css";

// The logo with a way to sign out, for every screen after signing in.
export function SignedInHeader() {
  const signOut = useSignOut();
  const [leaving, setLeaving] = useState(false);

  function handleSignOut() {
    setLeaving(true);
    void signOut();
  }

  return (
    <div className={styles.header}>
      <Logo />
      <button type="button" className={styles.signOut} onClick={handleSignOut} disabled={leaving}>
        {leaving ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
