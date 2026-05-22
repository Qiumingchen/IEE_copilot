export type NavigationItem = {
  label: string;
  href: string;
};

export const primaryNavigationItems: NavigationItem[] = [
  { label: "Dashboard", href: "/" },
  { label: "Search", href: "/search" },
  { label: "Curation", href: "/curation" }
];

export const utilityNavigationItems: NavigationItem[] = [{ label: "Sign in", href: "/login" }];

export function buildEnzymeNavigation(enzymeId: string): NavigationItem[] {
  const encodedId = encodeURIComponent(enzymeId);
  return [
    { label: "Overview", href: `/enzymes/${encodedId}` },
    { label: "Structures", href: `/enzymes/${encodedId}/structures` },
    { label: "Properties", href: `/enzymes/${encodedId}/properties` },
    { label: "Mutations", href: `/enzymes/${encodedId}/mutations` },
    { label: "Analysis", href: `/enzymes/${encodedId}/analysis` },
    { label: "Wet-lab data", href: `/enzymes/${encodedId}/experiments` }
  ];
}

export function enzymeIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/enzymes\/([^/]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function isNavigationItemActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  if (href.match(/^\/enzymes\/[^/]+$/)) {
    return pathname === href;
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function buildPageBreadcrumbs(pathname: string): NavigationItem[] {
  if (pathname === "/") {
    return [{ label: "Dashboard", href: "/" }];
  }

  const topLevelItem = primaryNavigationItems.find((item) => isNavigationItemActive(pathname, item.href));
  if (topLevelItem) {
    return [{ label: "Dashboard", href: "/" }, topLevelItem].filter(
      (item, index, items) => index === 0 || item.href !== items[index - 1]?.href
    );
  }

  const enzymeId = enzymeIdFromPath(pathname);
  if (!enzymeId) {
    return [{ label: "Dashboard", href: "/" }];
  }

  const enzymeNavigation = buildEnzymeNavigation(enzymeId);
  const currentSection = enzymeNavigation.find((item) => isNavigationItemActive(pathname, item.href));

  return [
    { label: "Dashboard", href: "/" },
    { label: "Search", href: "/search" },
    { label: "Current enzyme", href: `/enzymes/${encodeURIComponent(enzymeId)}` },
    ...(currentSection && currentSection.href !== `/enzymes/${encodeURIComponent(enzymeId)}` ? [currentSection] : [])
  ];
}
