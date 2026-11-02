import { Navigate, useNavigate } from "react-router-dom";
import { getToken } from "../api/session";
import footerShield from "../assets/icons/welcome-footer-shield.svg";
import mark from "../assets/icons/welcome-mark.svg";
import shieldInner from "../assets/icons/welcome-shield-inner.svg";
import shieldMiddle from "../assets/icons/welcome-shield-middle.svg";
import shieldOuter from "../assets/icons/welcome-shield-outer.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import styles from "./WelcomePage.module.css";

// Figma 19:5 "Welcome": where signed-out visitors start. Anyone signed in
// goes to /enroll, which shows the right step for their Voice ID.
export function WelcomePage() {
  const navigate = useNavigate();

  if (getToken()) {
    return <Navigate to="/enroll" replace />;
  }

  return (
    <Page>
      <Logo />

      <div className={styles.hero} aria-hidden="true">
        <img className={styles.outer} src={shieldOuter} alt="" width={233} height={261} />
        <img className={styles.middle} src={shieldMiddle} alt="" width={180} height={200} />
        <img className={styles.inner} src={shieldInner} alt="" width={116} height={130} />
        <img className={styles.mark} src={mark} alt="" width={138} height={90} />
        <span className={styles.badge}>Made for your voice</span>
      </div>

      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Your voice. Your security."
          title={
            <>
              Be yourself.{" "}
              <br />
              Stay protected.
            </>
          }
          subtitle="Your voice is one of a kind. Make it your most personal layer of protection."
        />
      </div>

      <div className={styles.actions}>
        <Button type="button" showArrow onClick={() => navigate("/signup")}>
          Get started
        </Button>
        <Button type="button" variant="secondary" onClick={() => navigate("/signin")}>
          I already have an account
        </Button>
      </div>

      <p className={styles.footer}>
        <img src={footerShield} alt="" width={9.59} height={10.67} />
        Private by design. Secure by default.
      </p>
    </Page>
  );
}
