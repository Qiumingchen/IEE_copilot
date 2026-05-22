"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";

import {
  buildPageBreadcrumbs,
  buildEnzymeNavigation,
  enzymeIdFromPath,
  isNavigationItemActive,
  primaryNavigationItems,
  utilityNavigationItems
} from "../lib/navigation";

const TOKEN_KEY = "iee-copilot-token";

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isSignedIn, setIsSignedIn] = useState(false);

  const enzymeId = useMemo(() => enzymeIdFromPath(pathname), [pathname]);
  const enzymeNavigationItems = useMemo(
    () => (enzymeId ? buildEnzymeNavigation(enzymeId) : []),
    [enzymeId]
  );
  const breadcrumbs = useMemo(() => buildPageBreadcrumbs(pathname), [pathname]);

  useEffect(() => {
    setIsSignedIn(Boolean(window.localStorage.getItem(TOKEN_KEY)));
  }, [pathname]);

  if (pathname === "/login") {
    return <>{children}</>;
  }

  function handleSignOut() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem("iee-copilot-token-type");
    setIsSignedIn(false);
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="grid min-w-0 gap-2">
            <Link className="min-w-0" href="/">
              <span className="block text-base font-semibold text-slate-950">IEE-Copilot</span>
              <span className="block truncate text-xs text-slate-500">
                Industrial enzyme engineering
              </span>
            </Link>
            <nav className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-slate-500" aria-label="Breadcrumb">
              {breadcrumbs.map((item, index) => {
                const isLast = index === breadcrumbs.length - 1;
                return (
                  <span className="flex min-w-0 items-center gap-1" key={`${item.href}-${index}`}>
                    {index > 0 ? <span aria-hidden="true">/</span> : null}
                    {isLast ? (
                      <span className="max-w-48 truncate font-medium text-slate-800">{item.label}</span>
                    ) : (
                      <Link className="max-w-48 truncate hover:text-slate-950" href={item.href}>
                        {item.label}
                      </Link>
                    )}
                  </span>
                );
              })}
            </nav>
          </div>

          <nav className="flex flex-wrap items-center gap-2 text-sm" aria-label="Utility navigation">
            {isSignedIn ? (
              <button
                className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white"
                onClick={handleSignOut}
                type="button"
              >
                Sign out
              </button>
            ) : (
              utilityNavigationItems.map((item) => (
                <Link
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-700"
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </Link>
              ))
            )}
          </nav>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-0 md:grid-cols-[220px_1fr]">
        <aside className="border-b border-slate-200 bg-white px-4 py-4 md:min-h-[calc(100vh-65px)] md:border-b-0 md:border-r md:px-5">
          <nav className="grid gap-1" aria-label="Primary navigation">
            {primaryNavigationItems.map((item) => (
              <Link
                className={`rounded-md px-3 py-2 text-sm font-medium ${
                  isNavigationItemActive(pathname, item.href)
                    ? "bg-slate-950 text-white"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {enzymeNavigationItems.length > 0 ? (
            <nav className="mt-5 border-t border-slate-200 pt-4" aria-label="Enzyme navigation">
              <p className="px-3 text-xs font-medium uppercase text-slate-500">Current enzyme</p>
              <div className="mt-2 grid gap-1">
                {enzymeNavigationItems.map((item) => (
                  <Link
                    className={`rounded-md px-3 py-2 text-sm font-medium ${
                      isNavigationItemActive(pathname, item.href)
                        ? "bg-slate-900 text-white"
                        : "text-slate-700 hover:bg-slate-100"
                    }`}
                    href={item.href}
                    key={item.href}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </nav>
          ) : null}
        </aside>

        <div className="min-w-0 bg-slate-50">{children}</div>
      </div>
    </div>
  );
}
