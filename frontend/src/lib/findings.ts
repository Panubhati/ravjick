/**
 * Which findings to show. Collapsed: the first `count` plus the last one,
 * because the last finding is always the small-sample caveat and must stay
 * visible.
 */
export function visibleFindings(findings: string[], expanded: boolean, count = 4): string[] {
  if (expanded || findings.length <= count + 1) return findings;
  return [...findings.slice(0, count), findings[findings.length - 1]];
}
