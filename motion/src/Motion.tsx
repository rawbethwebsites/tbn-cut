import { icons } from "lucide-react";
import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/** Icons Gemma may choose from (Lucide, MIT). Keep in sync with tbncut/motion.py ICONS. */
export const ICON_NAMES = Object.keys(icons);

/** A Lucide icon that draws its own strokes in, then settles with a small spring. */
export const DrawIcon: React.FC<{ name: string; size: number; color: string; delay?: number; strokeWidth?: number }> = ({
  name,
  size,
  color,
  delay = 0,
  strokeWidth = 2.2,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const Icon = (icons as Record<string, React.FC<React.SVGProps<SVGSVGElement> & { size?: number }>>)[name];
  if (!Icon) return null;
  const draw = interpolate(frame - delay, [0, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const pop = spring({ frame: frame - delay, fps, config: { damping: 11, stiffness: 220, mass: 0.6 } });
  return (
    <Icon
      size={size}
      color={color}
      strokeWidth={strokeWidth}
      style={{
        // stroke-dasharray/offset are inherited by every path in the icon, so the whole icon draws in
        strokeDasharray: 120,
        strokeDashoffset: (1 - draw) * 120,
        transform: `scale(${interpolate(pop, [0, 1], [0.6, 1])}) rotate(${interpolate(pop, [0, 1], [-12, 0])}deg)`,
        overflow: "visible",
      }}
    />
  );
};

/** Flat squares bursting out from a point on an entrance (no glow). */
export const Burst: React.FC<{ color: string; count?: number; radius?: number }> = ({ color, count = 8, radius = 170 }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.quad) });
  if (frame > 18) return null;
  return (
    <>
      {Array.from({ length: count }).map((_, i) => {
        const a = (i / count) * Math.PI * 2 + 0.3;
        const size = i % 2 ? 14 : 20;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: size,
              height: size,
              background: i % 3 === 0 ? "#FFFFFF" : color,
              borderRadius: i % 2 ? 3 : 10,
              transform: `translate(${Math.cos(a) * radius * t - size / 2}px, ${Math.sin(a) * radius * t - size / 2}px) rotate(${t * 180}deg) scale(${1 - t})`,
            }}
          />
        );
      })}
    </>
  );
};

/** Rings that ripple outward behind a full-screen title. */
export const Rings: React.FC<{ color: string }> = ({ color }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      {[0, 10, 20].map((d) => {
        const t = ((frame - d) % 45) / 45;
        if (frame < d) return null;
        return (
          <div
            key={d}
            style={{
              position: "absolute",
              width: 300 + t * 900,
              height: 300 + t * 900,
              borderRadius: "50%",
              border: `6px solid ${color}`,
              opacity: (1 - t) * 0.5,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** A ring that fills as a number counts up. */
export const ProgressRing: React.FC<{ progress: number; size: number; color: string }> = ({ progress, size, color }) => {
  const r = size / 2 - 12;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%) rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.18)" strokeWidth={14} fill="none" />
      <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={14} fill="none" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - progress)} />
    </svg>
  );
};

/** Hand-drawn underline that draws itself under a word. */
export const Scribble: React.FC<{ color: string; startFrame: number }> = ({ color, startFrame }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame - startFrame, [0, 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <svg viewBox="0 0 100 20" preserveAspectRatio="none" style={{ position: "absolute", left: "-4%", bottom: -14, width: "108%", height: 24, overflow: "visible" }}>
      <path d="M2 13 C 25 5, 55 18, 98 7" stroke={color} strokeWidth={5} fill="none" strokeLinecap="round"
        strokeDasharray={110} strokeDashoffset={(1 - p) * 110} vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

/** Transition on every cut: a punch zoom, a whip, or nothing. Wraps the camera video. */
export const CutFx: React.FC<{ cuts: number[]; kind: "punch" | "whip" | "none"; children: React.ReactNode }> = ({ cuts, kind, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (kind === "none") return <>{children}</>;
  const last = cuts.map((c) => Math.round(c * fps)).filter((c) => c <= frame && c > 0).pop();
  const d = last === undefined ? 99 : frame - last;
  let transform = "none";
  let filter = "none";
  if (d < 8) {
    if (kind === "punch") {
      transform = `scale(${interpolate(d, [0, 7], [1.1, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) })})`;
    } else {
      const k = (last ?? 0) % 2 ? 1 : -1;
      transform = `translateX(${interpolate(d, [0, 6], [k * 90, 0], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) })}px) scale(1.04)`;
      filter = `blur(${interpolate(d, [0, 5], [14, 0], { extrapolateRight: "clamp" })}px)`;
    }
  }
  const flash = interpolate(d, [0, 3], [0.16, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform, filter }}>{children}</AbsoluteFill>
      {flash > 0 ? <AbsoluteFill style={{ background: "#FFFFFF", opacity: flash }} /> : null}
    </AbsoluteFill>
  );
};
