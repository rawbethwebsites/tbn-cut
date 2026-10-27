/**
 * "OS" motion primitives, after cdsigrl.org's GSAP intro and desktop (Rob, 19 Oct 2026):
 *  - MaskRise: letters rise out of a mask, one after another (the boot wordmark)
 *  - Gauge: an arc draws itself, ticks pop in, a needle climbs then settles with an elastic bounce, a readout counts up
 *  - Shutter: two panels close over the end of a scene and split open (top up, bottom down) over the next
 *  - GenieWindow: a desktop window pours out of the dock (pinched clip + squash) and folds back at the end
 *  - Grid: the faint blueprint grid behind the boot screen
 * Which of these a video uses is decided by a motion template (templates/motion/*.json), never hard-coded.
 */
import React from "react";
import { AbsoluteFill, Easing, Img, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export type MotionPack = {
  title?: "spring" | "maskrise"; // how scene titles arrive
  stat?: "count" | "gauge"; // how a number arrives
  transition?: "fade" | "shutter"; // between scenes
  backdrop?: "plain" | "grid"; // behind every scene
  window?: "pop" | "genie"; // how a picture/screen recording arrives
  speed?: number; // 1 = cdsigrl.org timings; 0.8 slower, 1.2 faster
  stagger?: number; // seconds between letters in maskrise (cdsigrl.org: 0.045)
};

const power3Out = Easing.out(Easing.cubic);
const expoInOut = Easing.inOut(Easing.exp);
const clamp = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };

/** Letters rise from below a mask with a stagger; accent words in the accent colour. */
export const MaskRise: React.FC<{
  text: string; accent?: string; size: number; color: string; accentColor: string; font: string;
  align?: "left" | "center"; stagger?: number; speed?: number; delay?: number;
}> = ({ text, accent, size, color, accentColor, font, align = "left", stagger = 0.045, speed = 1, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const marks = new Set((accent ?? "").toUpperCase().split(/\s+/).filter(Boolean));
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);
  const dur = (0.8 / speed) * fps;
  let n = 0;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: `0 ${size * 0.22}px`, justifyContent: align === "center" ? "center" : "flex-start" }}>
      {words.map((w, i) => {
        const hot = marks.has(w.replace(/[^A-Z0-9']/g, ""));
        return (
          <span key={i} style={{ display: "inline-flex", overflow: "hidden", paddingBottom: size * 0.04, lineHeight: 1 }}>
            {[...w].map((ch, j) => {
              const start = delay + (n++ * stagger * fps) / speed;
              const k = interpolate(frame, [start, start + dur], [0, 1], { ...clamp, easing: power3Out });
              return (
                <span key={j} style={{ fontFamily: font, fontSize: size, lineHeight: 0.98, color: hot ? accentColor : color, display: "inline-block",
                                       transform: `translateY(${interpolate(k, [0, 1], [115, 0])}%)` }}>{ch}</span>
              );
            })}
          </span>
        );
      })}
    </div>
  );
};

/** A 270-degree gauge: arc draws, ticks stagger in, the needle climbs to 86% then snaps home with an elastic bounce. */
export const Gauge: React.FC<{
  value: number; unit?: string; label?: string; status?: string; ink: string; accent: string; track: string; font: string; ui: string; speed?: number;
}> = ({ value, unit = "", label, status, ink, accent, track, font, ui, speed = 1 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (sec: number) => (sec * fps) / speed;
  const R = 40, cx = 50, cy = 50, a0 = 135, sweep = 270;
  const pt = (deg: number, r = R) => [cx + r * Math.cos((deg * Math.PI) / 180), cy + r * Math.sin((deg * Math.PI) / 180)];
  const [x0, y0] = pt(a0), [x1, y1] = pt(a0 + sweep);
  const arc = `M ${x0} ${y0} A ${R} ${R} 0 1 1 ${x1} ${y1}`;
  const len = 2 * Math.PI * R * (sweep / 360);
  const draw = interpolate(frame, [0, s(1.1)], [len, 0], { ...clamp, easing: Easing.inOut(Easing.quad) });
  const climb = interpolate(frame, [s(0.7), s(2.0)], [0, 0.86], { ...clamp, easing: Easing.inOut(Easing.quad) });
  const settle = interpolate(frame, [s(2.0), s(3.0)], [0, 1], { ...clamp, easing: Easing.out(Easing.elastic(1.1)) });
  const f = climb + (1 - 0.86) * settle; // 0..1 (can overshoot a little on the bounce)
  const done = frame >= s(2.35);
  const shown = Math.min(1, f) * value;
  const needle = a0 + sweep * f; // degrees on the dial
  const [nx, ny] = pt(needle, R - 9);
  const ticks = Array.from({ length: 11 }, (_, i) => i);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginTop: 30 }}>
      <svg viewBox="0 0 100 100" width={760} height={760} style={{ overflow: "visible" }}>
        <path d={arc} fill="none" stroke={track} strokeWidth={3} strokeLinecap="round" />
        <path d={arc} fill="none" stroke={accent} strokeWidth={3} strokeLinecap="round" strokeDasharray={len} strokeDashoffset={draw} />
        {ticks.map((i) => {
          const deg = a0 + (sweep * i) / 10;
          const [ax, ay] = pt(deg, R - 4), [bx, by] = pt(deg, R - (i % 5 === 0 ? 9 : 6.5));
          const o = interpolate(frame, [s(0.25 + i * 0.04), s(0.5 + i * 0.04)], [0, 1], clamp);
          return <line key={i} x1={ax} y1={ay} x2={bx} y2={by} stroke={ink} strokeOpacity={0.55 * o} strokeWidth={0.8} />;
        })}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={ink} strokeWidth={1.6} strokeLinecap="round" opacity={interpolate(frame, [s(0.5), s(0.8)], [0, 1], clamp)} />
        <circle cx={cx} cy={cy} r={2.6} fill={accent} />
      </svg>
      <div style={{ marginTop: -170, fontFamily: font, fontSize: 200, lineHeight: 0.9, color: accent, fontVariantNumeric: "tabular-nums" }}>
        {Number.isInteger(value) ? Math.round(shown).toLocaleString() : shown.toFixed(1)}
        <span style={{ fontSize: 90, color: ink }}>{unit}</span>
      </div>
      {label ? <div style={{ fontFamily: ui, fontWeight: 800, fontSize: 30, letterSpacing: 6, color: ink, opacity: 0.7, marginTop: 14 }}>{label.toUpperCase()}</div> : null}
      {status ? (
        <div style={{ fontFamily: ui, fontWeight: 900, fontSize: 34, letterSpacing: 4, color: accent, marginTop: 16,
                      opacity: done ? 1 : 0, transform: `translateY(${done ? 0 : 10}px)` }}>✓ {status.toUpperCase()}</div>
      ) : null}
    </div>
  );
};

/** Two panels: they close over the last frames of a scene and split open over the first frames of the next. */
export const Shutter: React.FC<{ dur: number; color: string; seam?: string; first: boolean; last: boolean; speed?: number }> = ({ dur, color, seam, first, last, speed = 1 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const open = first ? 1 : interpolate(frame, [0, (0.75 * fps) / speed], [0, 1], { ...clamp, easing: expoInOut });
  const close = last ? 0 : interpolate(frame, [dur - (0.35 * fps) / speed, dur], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
  const k = Math.max(1 - open, close); // 1 = fully closed
  if (k <= 0.001) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: "50.5%", background: color, borderBottom: seam ? `6px solid ${seam}` : undefined, transform: `translateY(${-100 * (1 - k)}%)` }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: "50.5%", background: color, borderTop: seam ? `6px solid ${seam}` : undefined, transform: `translateY(${100 * (1 - k)}%)` }} />
    </AbsoluteFill>
  );
};

/** The blueprint grid behind the boot screen. */
export const Grid: React.FC<{ ink: string }> = ({ ink }) => (
  <AbsoluteFill style={{ backgroundImage: `linear-gradient(${ink}14 1px, transparent 1px), linear-gradient(90deg, ${ink}14 1px, transparent 1px)`,
                         backgroundSize: "90px 90px", maskImage: "radial-gradient(ellipse at center, #000 35%, transparent 80%)" }} />
);

/** A desktop window that pours out of the dock (bottom centre) and folds back into it at the end. */
export const GenieWindow: React.FC<{
  media: string; title?: string; dur: number; style: "pop" | "genie"; chrome: string; ink: string; ui: string; speed?: number;
}> = ({ media, title, dur, style, chrome, ink, ui, speed = 1 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (sec: number) => (sec * fps) / speed;
  const isVideo = /\.(mp4|mov|webm)$/i.test(media);
  const inK = interpolate(frame, [0, s(0.42)], [0, 1], { ...clamp, easing: power3Out });
  const clipK = interpolate(frame, [s(0.2), s(0.5)], [0, 1], { ...clamp, easing: Easing.out(Easing.quad) });
  const outK = interpolate(frame, [dur - s(0.6), dur - s(0.06)], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
  const k = inK * (1 - outK), c = clipK * (1 - outK);
  const px = 50; // the dock icon sits at the bottom centre
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  const clip = style === "genie"
    ? `polygon(0% 0%,100% 0%,${lerp(100 - (96 - px) * 0.25, 100, c)}% 45%,${lerp(px + 4, 100, c)}% 100%,${lerp(px - 4, 0, c)}% 100%,${lerp((px - 4) * 0.25, 0, c)}% 45%)`
    : "none";
  const sx = style === "genie" ? lerp(0.35, 1, k) : lerp(0.85, 1, k), sy = style === "genie" ? lerp(0.03, 1, k) : lerp(0.85, 1, k);
  return (
    <div style={{ width: 900, margin: "40px auto 0", transformOrigin: `${px}% 100%`, clipPath: clip,
                  transform: `translateY(${lerp(style === "genie" ? 700 : 60, 0, k)}px) scale(${sx}, ${sy})`, opacity: Math.min(1, k * 1.6) }}>
      <div style={{ borderRadius: 26, overflow: "hidden", background: chrome, boxShadow: "0 40px 90px rgba(0,0,0,0.45)", border: `2px solid ${ink}22` }}>
        <div style={{ height: 64, display: "flex", alignItems: "center", gap: 14, padding: "0 24px", background: `${ink}10` }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c2) => <span key={c2} style={{ width: 20, height: 20, borderRadius: 10, background: c2 }} />)}
          <span style={{ fontFamily: ui, fontWeight: 800, fontSize: 24, color: ink, opacity: 0.75, marginLeft: 12 }}>{title ?? ""}</span>
        </div>
        <div style={{ aspectRatio: "4 / 3", background: "#000" }}>
          {isVideo
            ? <OffthreadVideo src={staticFile(media)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <Img src={staticFile(media)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />}
        </div>
      </div>
    </div>
  );
};
