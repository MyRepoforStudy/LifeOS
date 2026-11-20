import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import { useI18n } from "../i18n";
import { Icon, type IconName } from "./Icon";

const LINKS: {
  to: string;
  icon: IconName;
  label: "nav.home" | "nav.quests" | "nav.habits" | "nav.cycles" | "nav.profile";
  end?: boolean;
}[] = [
  { to: "/", icon: "home", label: "nav.home", end: true },
  { to: "/quests", icon: "target", label: "nav.quests" },
  { to: "/habits", icon: "flame", label: "nav.habits" },
  { to: "/cycles", icon: "cycle", label: "nav.cycles" },
  { to: "/profile", icon: "user", label: "nav.profile" },
];

export function Layout() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  // A new page starts at the top instead of the scroll position of the previous one.
  // Block body: newer browsers return a Promise from scrollTo, and an effect must not
  // return anything but a cleanup function.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
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
