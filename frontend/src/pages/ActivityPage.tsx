import { Link } from "react-router-dom";
import { getActivity, type ActivityEvent, type ActivityKind } from "../api/activity";
import summaryShield from "../assets/icons/activity-summary-shield.svg";
import rowLock from "../assets/icons/row-lock.svg";
import rowMic from "../assets/icons/row-mic.svg";
import rowShield from "../assets/icons/row-shield.svg";
import { Logo } from "../components/Logo";
import { Page } from "../components/Page";
import { PageHeading } from "../components/PageHeading";
import { TabBar } from "../components/TabBar";
import { useSignedInData } from "../hooks/useSignedInData";
import styles from "./ActivityPage.module.css";

type Icon = { src: string; width: number; height: number };
const MIC: Icon = { src: rowMic, width: 13.13, height: 18.88 };
const LOCK: Icon = { src: rowLock, width: 15.05, height: 18.88 };
const SHIELD: Icon = { src: rowShield, width: 16.96, height: 18.88 };

// How each event reads. "Look" marks the ones worth a second glance: they may
// be someone else trying the account. No device or place: the server keeps
// neither (see the privacy note).
const EVENTS: Record<ActivityKind, { title: string; detail: string; icon: Icon; look?: boolean }> = {
  voice_check_approved: { title: "Voice verification", detail: "Your voice was confirmed", icon: MIC },
  voice_check_rejected: {
    title: "Voice check failed",
    detail: "The recording wasn’t accepted",
    icon: MIC,
    look: true,
  },
  voice_check_incomplete: { title: "Voice check incomplete", detail: "No Voice ID to compare with yet", icon: MIC },
  voice_checks_paused: {
    title: "Voice checks paused",
    // How many and how long are server settings (VOICE_MAX_FAILURES,
    // VOICE_LOCKOUT_SECONDS), so no numbers here.
    detail: "Too many failed checks",
    icon: MIC,
    look: true,
  },
  login_succeeded: { title: "Secure sign in", detail: "Password accepted", icon: LOCK },
  login_failed: { title: "Wrong password", detail: "Someone typed a wrong password", icon: LOCK, look: true },
  login_locked: { title: "Sign-in locked", detail: "Too many wrong passwords", icon: LOCK, look: true },
  logout: { title: "Signed out", detail: "Your session ended", icon: LOCK },
  signup: { title: "Account created", detail: "Welcome to VoiceGuard", icon: SHIELD },
  email_verified: { title: "Email confirmed", detail: "Your address was confirmed", icon: SHIELD },
  enrolled: { title: "Voice ID created", detail: "Your voiceprint was encrypted", icon: SHIELD },
};

// The server sends at most this many (backend audit.ACTIVITY_LIMIT).
const MOST_SHOWN = 50;

const TIME = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });
const DAY = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" });

function startOfDay(moment: Date): number {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime();
}

function dayLabel(moment: Date, now: Date): string {
  const days = Math.round((startOfDay(now) - startOfDay(moment)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return DAY.format(moment);
}

function timeLabel(moment: Date, now: Date): string {
  return now.getTime() - moment.getTime() < 60_000 ? "Just now" : TIME.format(moment);
}

// Newest first, grouped by day, as they come from the server.
function byDay(events: ActivityEvent[], now: Date): { day: string; events: ActivityEvent[] }[] {
  const groups: { day: string; events: ActivityEvent[] }[] = [];
  for (const event of events) {
    const day = dayLabel(new Date(event.at), now);
    const last = groups.at(-1);
    if (last?.day === day) last.events.push(event);
    else groups.push({ day, events: [event] });
  }
  return groups;
}

// The user's security timeline, from Figma 19:476.
export function ActivityPage() {
  const { data: events, error } = useSignedInData(getActivity);
  const now = new Date();
  const toLook = events?.filter((event) => EVENTS[event.kind].look).length ?? 0;

  return (
    <Page>
      <Logo />
      <div className={styles.heading}>
        <PageHeading
          showBadge={false}
          eyebrow="Your security timeline"
          title="Nothing goes unnoticed."
          subtitle="Keep an eye on when and how your identity is used."
        />
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {!events && !error && <p className={styles.status}>Loading your activity…</p>}

      {events && (
        <>
          <section className={styles.summary} aria-label="The last 30 days">
            <span className={styles.count}>
              {events.length >= MOST_SHOWN ? `${MOST_SHOWN}+` : String(events.length).padStart(2, "0")}
            </span>
            <span className={styles.summaryText}>
              <span className={styles.summaryTitle}>{toLook ? "Security events" : "Secure events"}</span>
              <span className={styles.summaryDetail}>
                {events.length === 0
                  ? "Nothing in the last 30 days"
                  : toLook
                    ? `${toLook} worth a look`
                    : "Everything looks good"}
              </span>
            </span>
            <img src={summaryShield} alt="" width={19.91} height={22.16} />
          </section>

          {byDay(events, now).map((group) => (
            <section key={group.day} aria-label={group.day}>
              <h2 className={styles.day}>{group.day}</h2>
              <ul className={styles.events}>
                {group.events.map((event, index) => {
                  const shown = EVENTS[event.kind];
                  return (
                    <li key={`${event.at}-${index}`} className={styles.event}>
                      <span className={styles.icon}>
                        <img src={shown.icon.src} alt="" width={shown.icon.width} height={shown.icon.height} />
                      </span>
                      <span className={styles.text}>
                        <span className={styles.title}>{shown.title}</span>
                        <span className={styles.detail}>{shown.detail}</span>
                        <time className={styles.detail} dateTime={event.at}>
                          {timeLabel(new Date(event.at), now)}
                        </time>
                      </span>
                      {/* The dot's colour alone can't say it (WCAG 1.4.1), so screen readers get words. */}
                      {shown.look && <span className={styles.visuallyHidden}>Worth a look</span>}
                      <span className={shown.look ? styles.lookDot : styles.dot} aria-hidden="true" />
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}

          <p className={styles.note}>
            Don’t recognise something here? <Link to="/forgot-password">Change your password</Link> and tell the
            VoiceGuard team.
          </p>
        </>
      )}

      <TabBar />
    </Page>
  );
}
