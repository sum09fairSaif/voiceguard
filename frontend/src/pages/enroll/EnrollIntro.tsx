import { useState } from "react";
import checkboxTick from "../../assets/icons/checkbox-tick.svg";
import featureLock from "../../assets/icons/feature-lock.svg";
import featureMic from "../../assets/icons/feature-mic.svg";
import featureShield from "../../assets/icons/feature-shield.svg";
import voiceIdMark from "../../assets/icons/voice-id-mark.svg";
import { Button } from "../../components/Button";
import { PageHeading } from "../../components/PageHeading";
import { StepProgress } from "../../components/StepProgress";
import styles from "./EnrollIntro.module.css";

const FEATURES = [
  { icon: featureMic, width: 12.56, height: 18.06, title: "Speak, don’t remember", text: "A short phrase is all it takes." },
  { icon: featureLock, width: 14.39, height: 18.06, title: "Yours. And only yours.", text: "Your voiceprint is stored encrypted." },
  { icon: featureShield, width: 16.23, height: 18.06, title: "Built for peace of mind", text: "An extra layer for your identity." },
];

// Figma 1:188 "Set up Voice ID": step 1 of enrollment. Voice is biometric
// data, so the consent box must be ticked before recording can start.
export function EnrollIntro({ onStart }: { onStart: () => void }) {
  const [agreed, setAgreed] = useState(false);

  return (
    <>
      <div className={styles.progress}>
        <StepProgress current={1} total={3} />
      </div>
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Voice ID / 01"
          title={
            <>
              Meet your{" "}
              <br />
              new key.
            </>
          }
          subtitle="No two voices are alike. Set up your Voice ID in just a few seconds."
        />
      </div>

      <div className={styles.mark}>
        <img src={voiceIdMark} alt="" width={96.6} height={63} />
      </div>

      <ul className={styles.features}>
        {FEATURES.map((feature) => (
          <li key={feature.title} className={styles.feature}>
            <span className={styles.featureIcon}>
              <img src={feature.icon} alt="" width={feature.width} height={feature.height} />
            </span>
            <span>
              <p className={styles.featureTitle}>{feature.title}</p>
              <p className={styles.featureText}>{feature.text}</p>
            </span>
          </li>
        ))}
      </ul>

      <label className={styles.consent}>
        <input
          type="checkbox"
          className={styles.consentInput}
          checked={agreed}
          onChange={(event) => setAgreed(event.target.checked)}
        />
        <span className={styles.box} aria-hidden="true">
          {agreed && <img src={checkboxTick} alt="" width={8.5} height={6.34} />}
        </span>
        <span>I agree to use my voice to create a secure Voice ID.</span>
      </label>

      <div className={styles.action}>
        <Button type="button" showArrow disabled={!agreed} onClick={onStart}>
          Set up my Voice ID
        </Button>
      </div>
    </>
  );
}
