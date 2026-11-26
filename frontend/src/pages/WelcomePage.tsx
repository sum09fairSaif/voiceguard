import { Navigate, useNavigate } from "react-router-dom";
import { isSignedIn } from "../api/session";
import footerShield from "../assets/icons/welcome-footer-shield.svg";
import mark from "../assets/icons/welcome-mark.svg";
import shieldInner from "../assets/icons/welcome-shield-inner.svg";
import shieldMiddle from "../assets/icons/welcome-shield-middle.svg";
import shieldOuter from "../assets/icons/welcome-shield-outer.svg";
import tabletMark from "../assets/icons/welcome-tablet-mark.svg";
import tabletShieldInner from "../assets/icons/welcome-tablet-shield-inner.svg";
import tabletShieldMiddle from "../assets/icons/welcome-tablet-shield-middle.svg";
import tabletShieldOuter from "../assets/icons/welcome-tablet-shield-outer.svg";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { Columns, Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import styles from "./WelcomePage.module.css";

// Figma 19:5 "Welcome" (tablet: 141:2): where signed-out visitors start. Anyone signed in
// goes to /enroll, which shows the right step for their Voice ID.
export function WelcomePage() {
  const navigate = useNavigate();

  if (isSignedIn()) {
    return <Navigate to="/enroll" replace />;
  }

  return (
    <Page header={<Logo />}>
      <Columns
        aside={
          <>
            <div className={styles.hero} aria-hidden="true">
              <img className={styles.outer} src={shieldOuter} alt="" width={233} height={261} />
              <img className={styles.middle} src={shieldMiddle} alt="" width={180} height={200} />
              <img className={styles.inner} src={shieldInner} alt="" width={116} height={130} />
              <img className={styles.mark} src={mark} alt="" width={138} height={90} />
              <span className={styles.badge}>Made for your voice</span>
            </div>
            {/* Figma 141:2: the tablet's larger shields, with the badge under them. */}
            <div className={styles.heroTablet} aria-hidden="true">
              <img className={styles.outer} src={tabletShieldOuter} alt="" width={349} height={391} />
              <img className={styles.middle} src={tabletShieldMiddle} alt="" width={269.5} height={299.5} />
              <img className={styles.inner} src={tabletShieldInner} alt="" width={173.5} height={194.5} />
              <img className={styles.mark} src={tabletMark} alt="" width={201} height={129} />
              <span className={styles.badge}>Made for your voice</span>
            </div>
          </>
        }
      >
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
      </Columns>
    </Page>
  );
}
