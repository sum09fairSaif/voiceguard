import { NavLink } from "react-router-dom";
import activityIcon from "../assets/icons/tab-activity.svg";
import activityActiveIcon from "../assets/icons/tab-activity-active.svg";
import homeIcon from "../assets/icons/tab-home.svg";
import homeActiveIcon from "../assets/icons/tab-home-active.svg";
import settingsIcon from "../assets/icons/tab-settings.svg";
import settingsActiveIcon from "../assets/icons/tab-settings-active.svg";
import styles from "./TabBar.module.css";

type Tab = {
  to: string;
  label: string;
  icon: { src: string; activeSrc: string; width: number; height: number };
};

const TABS: Tab[] = [
  { to: "/account", label: "Home", icon: { src: homeIcon, activeSrc: homeActiveIcon, width: 18.88, height: 18.88 } },
  {
    to: "/activity",
    label: "Activity",
    icon: { src: activityIcon, activeSrc: activityActiveIcon, width: 18.88, height: 15.05 },
  },
  {
    to: "/settings",
    label: "Settings",
    icon: { src: settingsIcon, activeSrc: settingsActiveIcon, width: 16.96, height: 18.92 },
  },
];

// The bar along the foot of the signed-in screens (Figma 19:413, 19:476, 19:545).
export function TabBar() {
  return (
    <nav className={styles.bar} aria-label="Main">
      {TABS.map((tab) => (
        <NavLink key={tab.to} to={tab.to} className={({ isActive }) => (isActive ? styles.active : styles.tab)}>
          {({ isActive }) => (
            <>
              <span className={styles.icon}>
                <img
                  src={isActive ? tab.icon.activeSrc : tab.icon.src}
                  alt=""
                  width={tab.icon.width}
                  height={tab.icon.height}
                />
              </span>
              {tab.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
