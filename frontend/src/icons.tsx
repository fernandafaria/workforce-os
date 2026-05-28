/* global React */
// Executive Brain icon system — v2
// 3 category glyphs (filled, geometric) + outline chrome.
// Original work — geometric progression: half-disc → 2 circles → 3 circles.

import type { ReactNode, CSSProperties } from 'react';

const Svg = ({ size = 20, children, fill = "none", style }: { size?: number; children: ReactNode; fill?: string; style?: CSSProperties }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
    style={style}
    aria-hidden="true"
  >
    {children}
  </svg>
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const I: Record<string, (_p: any) => ReactNode> = {
  // ─── Category glyphs (filled, sober, Work & Co geometric) ────────────────

  // Ping / Manhã — sunrise: filled half-disc above a horizon line.
  // Reads as morning brief without "rays / sparkles" cliché.
  sun: (p) => (
    <Svg {...p}>
      <path d="M5.5 15a6.5 6.5 0 0 1 13 0Z" fill="currentColor" stroke="none" />
      <path d="M3 15.5h18" />
      <path d="M12 6v1.6" opacity=".55" />
    </Svg>
  ),

  // Conselho 1:1 — two overlapping circles, one solid (advisor presence),
  // one outlined (you). Dialogue without the chat-bubble trope.
  message: (p) => (
    <Svg {...p}>
      <circle cx="9.5" cy="12" r="5" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="12" r="5" />
    </Svg>
  ),

  // Grupo — three filled discs in a triangle composition. Convening of voices.
  people: (p) => (
    <Svg {...p}>
      <circle cx="12" cy="6.5" r="3.2" fill="currentColor" stroke="none" />
      <circle cx="6.5" cy="16" r="3.2" fill="currentColor" stroke="none" />
      <circle cx="17.5" cy="16" r="3.2" fill="currentColor" stroke="none" />
    </Svg>
  ),

  // ─── Chrome — thin outline, careful corners ──────────────────────────────

  search: (p) => (
    <Svg {...p}>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="m20 20-4.6-4.6" />
    </Svg>
  ),

  plus: (p) => (
    <Svg {...p}>
      <path d="M12 5.5v13M5.5 12h13" />
    </Svg>
  ),

  chevron: (p) => (
    <Svg {...p}>
      <path d="m9.5 6 6 6-6 6" />
    </Svg>
  ),

  back: (p) => (
    <Svg {...p}>
      <path d="m14.5 6-6 6 6 6" />
    </Svg>
  ),

  // iMessage-style upward send arrow
  send: (p) => (
    <Svg {...p}>
      <path d="M12 19V5" strokeWidth="2" />
      <path d="m6 11 6-6 6 6" strokeWidth="2" />
    </Svg>
  ),

  more: (p) => (
    <Svg {...p} fill="currentColor">
      <circle cx="5.5" cy="12" r="1.4" stroke="none" />
      <circle cx="12" cy="12" r="1.4" stroke="none" />
      <circle cx="18.5" cy="12" r="1.4" stroke="none" />
    </Svg>
  ),

  // Tag-shape pin (Aesop-style minimal)
  pin: (p) => (
    <Svg {...p}>
      <path d="M4 12.5 11.5 5l7.5 7.5-3 3-1.5-1.5-4 4-1.6-1.6-3-3Z" />
      <path d="m11 16-3 4" />
    </Svg>
  ),

  clock: (p) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4.3l2.8 1.6" />
    </Svg>
  ),

  copy: (p) => (
    <Svg {...p}>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2.2" />
      <path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" />
    </Svg>
  ),

  archive: (p) => (
    <Svg {...p}>
      <rect x="3.5" y="5.5" width="17" height="4" rx="1.4" />
      <path d="M5 9.5v8.6a1.4 1.4 0 0 0 1.4 1.4h11.2a1.4 1.4 0 0 0 1.4-1.4V9.5" />
      <path d="M10 13.5h4" />
    </Svg>
  ),

  check: (p: Record<string, unknown>) => (
    <Svg {...p} style={(p.style as CSSProperties) ?? undefined}>
      <path d="m5 12.5 4.5 4.5L20 6.5" strokeWidth="1.8" />
    </Svg>
  ),

  pause: (p) => (
    <Svg {...p} fill="currentColor">
      <rect x="8" y="5.5" width="3" height="13" rx="1" stroke="none" />
      <rect x="13" y="5.5" width="3" height="13" rx="1" stroke="none" />
    </Svg>
  ),

  external: (p) => (
    <Svg {...p}>
      <path d="M13.5 4.5h6v6" />
      <path d="M19.5 4.5 11 13" />
      <path d="M19 14v4.5A1.5 1.5 0 0 1 17.5 20h-12A1.5 1.5 0 0 1 4 18.5v-12A1.5 1.5 0 0 1 5.5 5H10" />
    </Svg>
  ),

  spark: (p) => (
    <Svg {...p} fill="currentColor">
      <path d="M12 3.5 13.6 9 19 10.6 13.6 12.2 12 17.5 10.4 12.2 5 10.6 10.4 9Z"
            stroke="none" />
    </Svg>
  ),
  // Lock — criptografia (Apple Notes Locked vibe, mínimo)
  lock: (p) => (
    <Svg {...p}>
      <rect x="5" y="11" width="14" height="9" rx="1.6" />
      <path d="M8 11V8.2a4 4 0 0 1 8 0V11" />
    </Svg>
  ),

  // Trash — descartar
  trash: (p) => (
    <Svg {...p}>
      <path d="M5 7h14" />
      <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" />
      <path d="M7 7v11.5A1.5 1.5 0 0 0 8.5 20h7a1.5 1.5 0 0 0 1.5-1.5V7" />
    </Svg>
  ),

};

(window as Window & { EBIcons?: typeof I }).EBIcons = I;
