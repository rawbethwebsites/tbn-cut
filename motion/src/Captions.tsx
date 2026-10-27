import React, { useMemo } from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily } from "./fonts";
import { Scribble } from "./Motion";
import { Style, Word } from "./types";

const SMALL = new Set([
  "a", "an", "the", "to", "of", "and", "or", "but", "so", "i", "you", "it", "is", "are", "was", "be", "in", "on",
  "at", "for", "my", "your", "me", "we", "he", "she", "they", "that", "this", "just", "like", "if", "as", "with",
  "i'll", "i'm", "it's", "he'll", "you'll", "do", "don't", "can", "will", "then", "now",
]);

const bare = (w: string) => w.toLowerCase().replace(/[^a-z0-9']/g, "");

/** Pages of up to maxWords, broken early at sentence ends and pauses. */
const paginate = (words: Word[], maxWords: number): Word[][] => {
  const pages: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    cur.push(w);
    const next = words[i + 1];
    // Never leave a lonely word: sentence ends and pauses only break once a page has 2+ words.
    const helpers = cur.filter((x) => !SMALL.has(bare(x.w))).length;
    const soft = cur.length >= 2 && helpers >= 1 && (/[.!?]$/.test(w.w) || (next && next.s - w.e > 0.35));
    const end = soft || cur.length >= maxWords || (next && next.s - w.e > 1.2);
    if (end || !next) {
      pages.push(cur);
      cur = [];
    }
  });
  return pages;
};

/** The one word per page that carries the meaning: a number, else the longest content word. */
const heroIndex = (page: Word[]): number => {
  let best = -1;
  let bestScore = 0;
  page.forEach((w, i) => {
    const b = bare(w.w);
    if (SMALL.has(b)) return;
    const score = (/\d/.test(b) ? 100 : 0) + b.length;
    if (score > bestScore && b.length >= 4) {
      best = i;
      bestScore = score;
    }
  });
  return best;
};

type Spot = { y: number; align: "center" | "flex-start" | "flex-end"; top?: boolean };

/** Where pages may sit: under the face (most of the time) and above it, never on it. */
const spotsFor = (face?: { top: number; bottom: number }): Spot[] => {
  const below = Math.min(0.86, Math.max(0.62, (face?.bottom ?? 0.6) + 0.1));
  const low = Math.min(0.88, below + 0.07);
  const above = Math.max(0.16, Math.min(0.3, (face?.top ?? 0.3) - 0.1));
  return [
    { y: below, align: "center" },
    { y: low, align: "flex-start" },
    { y: below, align: "flex-end" },
    { y: above, align: "center", top: true },
    { y: low, align: "center" },
  ];
};

type Props = {
  words: Word[];
  style: Style;
  hidden?: boolean;
  busySide?: (s: number, e: number) => "top" | "bottom" | null; // where a graphic shows during this page
  face?: { top: number; bottom: number };
};

/** All-caps Poppins captions with a big hero word, small helper words and a position that moves page to page. */
export const Captions: React.FC<Props> = ({ words, style, hidden, busySide, face }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const t = frame / fps;
  const pages = useMemo(() => paginate(words, style.maxWords), [words, style.maxWords]);
  const pi = pages.findIndex((p, i) => t >= p[0].s - 0.05 && t < (pages[i + 1]?.[0].s ?? p[p.length - 1].e + 0.6));
  if (pi < 0 || hidden) return null;
  const page = pages[pi];
  const hero = heroIndex(page);

  // Same page -> same spot (deterministic), skipping the top spot while a graphic is up there.
  const spots = spotsFor(face);
  const busy = busySide?.(page[0].s, page[page.length - 1].e + 0.3) ?? null;
  let spot: Spot =
    style.captionMode === "fixed"
      ? // one spot, pushed out of the face band if it would land on it
        (() => {
          const y = style.captionY;
          const f = face ?? { top: 0.3, bottom: 0.6 };
          if (y > f.top - 0.04 && y < f.bottom + 0.04) return { y: Math.min(0.86, f.bottom + 0.1), align: "center" as const };
          return { y, align: "center" as const, top: y < 0.5 };
        })()
      : spots[(pi * 7 + 3) % spots.length];
  if (busy === "top" && spot.top) spot = spots[0];
  if (busy === "bottom" && !spot.top) spot = spots[3];
  const pageIn = spring({ frame: frame - page[0].s * fps + 2, fps, config: { damping: 16, stiffness: 200 } });
  const base = style.captionSize;
  const tilt = hero >= 0 && pi % 3 === 1 ? -3 : 0;

  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        right: 80,
        top: height * spot.y,
        transform: `translateY(-50%) scale(${interpolate(pageIn, [0, 1], [0.94, 1])})`,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: spot.align,
        alignItems: "baseline",
        gap: "0px 18px",
        fontFamily: fontFamily(style.font),
        textTransform: style.uppercase === false ? "none" : "uppercase",
        lineHeight: 1.0,
      }}
    >
      {page.map((w, i) => {
        const isHero = i === hero;
        const small = hero >= 0 && SMALL.has(bare(w.w)); // with no hero word, keep everything readable
        const size = isHero ? base * 1.75 : small ? base * 0.72 : base;
        const inF = (w.s - 0.04) * fps;
        const pop = spring({ frame: frame - inF, fps, config: { damping: 12, stiffness: 240, mass: 0.6 } });
        const active = t >= w.s - 0.02 && t < (page[i + 1]?.s ?? w.e + 0.25);
        const shown = frame >= inF;
        return (
          <React.Fragment key={`${w.s}-${i}`}>
            {/* the hero word gets its own line */}
            {isHero && i > 0 ? <div style={{ flexBasis: "100%", height: 0 }} /> : null}
            <span
              style={{
                position: "relative",
                display: "inline-block",
                fontSize: size,
                fontWeight: isHero ? 900 : small ? 700 : 800,
                letterSpacing: isHero ? -2 : -0.5,
                color: active ? style.accent : style.text ?? "#FFFFFF",
                opacity: shown ? pop : 0,
                transform: `translateY(${interpolate(pop, [0, 1], [isHero ? 30 : 14, 0])}px) scale(${interpolate(
                  pop,
                  [0, 1],
                  [isHero ? 1.35 : 0.9, active ? 1.06 : 1],
                )}) rotate(${isHero ? tilt : 0}deg)`,
                textShadow: "0 4px 0 rgba(0,0,0,0.55), 0 6px 18px rgba(0,0,0,0.45)",
                WebkitTextStroke: isHero ? "0px" : "1.5px rgba(0,0,0,0.35)",
              }}
            >
              {w.w.replace(/[,;:]+$/, "")}
              {isHero && pi % 2 === 0 ? <Scribble color={style.accent} startFrame={Math.round(w.e * fps)} /> : null}
            </span>
            {isHero && i < page.length - 1 ? <div style={{ flexBasis: "100%", height: 0 }} /> : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};
