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
    { label: "Detail", href: `/enzymes/${encodedId}` },
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
