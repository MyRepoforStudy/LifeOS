import { NavLink, Outlet } from "react-router";

import { useI18n } from "../i18n";
import { Icon, type IconName } from "./Icon";

const LINKS: { to: string; icon: IconName; label: "nav.home" | "nav.quests" | "nav.profile"; end?: boolean }[] = [
  { to: "/", icon: "home", label: "nav.home", end: true },
  { to: "/quests", icon: "target", label: "nav.quests" },
  { to: "/profile", icon: "user", label: "nav.profile" },
];

export function Layout() {
  const { t } = useI18n();
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" />
          LifeOS
        </div>
        <nav aria-label="LifeOS">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {t(link.label)}
            </NavLink>
          ))}
        </nav>
      </header>
      <Outlet />
      <nav className="tabbar" aria-label="LifeOS">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end}>
            <Icon name={link.icon} />
            {t(link.label)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
