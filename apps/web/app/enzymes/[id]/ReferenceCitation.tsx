import type { LiteratureReferenceRecord } from "../../../lib/types";
import { buildReferenceHref, formatReferenceCitation } from "./reference-utils.ts";

type ReferenceCitationProps = {
  fallback?: string | null;
  reference?: LiteratureReferenceRecord | null;
};

export function ReferenceCitation({ fallback = null, reference = null }: ReferenceCitationProps) {
  if (!reference) {
    return <>{fallback || "-"}</>;
  }

  const label = formatReferenceCitation(reference);
  const href = buildReferenceHref(reference);
  if (!href) {
    return <>{label}</>;
  }

  return (
    <a
      className="font-medium text-slate-900 underline decoration-slate-300 underline-offset-2 hover:decoration-slate-900"
      href={href}
      rel="noreferrer"
      target="_blank"
    >
      {label}
    </a>
  );
}
