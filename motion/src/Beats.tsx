import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { fontFamily } from "./fonts";
import { Burst, DrawIcon, ProgressRing, Rings } from "./Motion";
import { Beat, Style } from "./types";

/** Where card graphics sit: top (default) or bottom, per template. */
const slot = (style: Style, pad: number): React.CSSProperties =>
  style.graphicsAt === "panel"
    ? { justifyContent: "center", alignItems: "center" }
    : style.graphicsAt === "bottom"
    ? { justifyContent: "flex-end", alignItems: "center", paddingBottom: pad + 120 }
    : { justifyContent: "flex-start", alignItems: "center", paddingTop: pad };

/** Shared in/out envelope: spring in, quick fade out over the last 8 frames. */
const useEnvelope = (durationInFrames: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 13, stiffness: 180, mass: 0.7 } });
  const exit = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return { frame, fps, enter, exit };
};

const Hook: React.FC<{ text: string; style: Style; dur: number }> = ({ text, style, dur }) => {
  const { frame, fps, exit } = useEnvelope(dur);
  const words = text.split(" ");
  return (
    <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center", paddingTop: 230, opacity: exit }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 22px", maxWidth: 900 }}>
        {words.map((w, i) => {
          const p = spring({ frame: frame - i * 3, fps, config: { damping: 11, stiffness: 260, mass: 0.6 } });
          return (
            <span
              key={i}
              style={{
                fontFamily: fontFamily(style.font),
                fontWeight: 900,
                fontSize: 108,
                lineHeight: 1.02,
                letterSpacing: -2,
                color: i === words.length - 1 ? style.accent : "#FFFFFF",
                textShadow: "0 6px 30px rgba(0,0,0,0.6)",
                transform: `translateY(${interpolate(p, [0, 1], [-60, 0])}px) scale(${interpolate(p, [0, 1], [1.4, 1])})`,
                opacity: p,
                display: "inline-block",
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Keyword: React.FC<{ text: string; icon?: string; style: Style; dur: number }> = ({ text, icon, style, dur }) => {
  const { enter, exit, frame } = useEnvelope(dur);
  const wobble = Math.sin(frame / 9) * 1.2;
  return (
    <AbsoluteFill style={slot(style, 300)}>
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 18 }}>
      <Burst color={style.accent} />
      {icon ? (
        <div
          style={{
            width: 132,
            height: 132,
            borderRadius: 66,
            background: "#FFFFFF",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
            transform: `scale(${interpolate(enter, [0, 1], [0.3, 1])})`,
            opacity: exit,
          }}
        >
          <DrawIcon name={icon} size={78} color={style.ink} delay={2} />
        </div>
      ) : null}
      <div
        style={{
          fontFamily: fontFamily(style.font),
          fontWeight: 900,
          fontSize: 84,
          color: style.ink,
          background: style.accent,
          padding: "18px 40px",
          borderRadius: 28,
          boxShadow: "0 18px 50px rgba(0,0,0,0.35)",
          transform: `scale(${interpolate(enter, [0, 1], [0.5, 1])}) rotate(${-3 + wobble}deg)`,
          opacity: Math.min(enter, exit),
          letterSpacing: -1,
        }}
      >
        {text}
      </div>
      </div>
    </AbsoluteFill>
  );
};

const List: React.FC<{ text: string; items: string[]; at?: number[]; style: Style; dur: number }> = ({ text, items, at, style, dur }) => {
  const { frame, fps, enter, exit } = useEnvelope(dur);
  const step = Math.max(6, Math.floor((dur - 20) / Math.max(1, items.length)));
  // Each item lands just before it's spoken; without timings, spread them evenly.
  const startOf = (i: number) => (at && at[i] !== undefined ? Math.round(at[i] * fps) - 4 : 8 + i * step);
  return (
    <AbsoluteFill style={{ ...slot(style, 180), opacity: exit }}>
      <div
        style={{
          width: 820,
          padding: "36px 44px",
          borderRadius: 36,
          background: "rgba(11,11,11,0.82)",
          border: `3px solid ${style.accent}`,
          transform: `translateY(${interpolate(enter, [0, 1], [-80, 0])}px)`,
          opacity: enter,
          fontFamily: fontFamily(style.font),
        }}
      >
        <div style={{ color: style.accent, fontWeight: 800, fontSize: 40, marginBottom: 18, letterSpacing: 1 }}>
          {text.toUpperCase()}
        </div>
        {items.map((it, i) => {
          const p = spring({ frame: frame - startOf(i), fps, config: { damping: 14, stiffness: 200 } });
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                fontSize: 54,
                fontWeight: 800,
                color: "#fff",
                margin: "10px 0",
                opacity: p,
                transform: `translateX(${interpolate(p, [0, 1], [-40, 0])}px)`,
              }}
            >
              <span
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 24,
                  background: style.accent,
                  color: style.ink,
                  fontSize: 30,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                ✓
              </span>
              {it}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Stat: React.FC<{ beat: Extract<Beat, { type: "stat" }>; style: Style; dur: number }> = ({ beat, style, dur }) => {
  const { frame, enter, exit } = useEnvelope(dur);
  const n = interpolate(frame, [0, Math.max(1, Math.min(dur - 10, 24))], [0, beat.value], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const shown = Number.isInteger(beat.value) ? Math.round(n).toLocaleString() : n.toFixed(1);
  return (
    <AbsoluteFill style={{ ...slot(style, 220), opacity: exit }}>
      <div style={{ position: "relative", textAlign: "center", fontFamily: fontFamily(style.font), transform: `scale(${interpolate(enter, [0, 1], [0.7, 1])})` }}>
        <ProgressRing progress={interpolate(frame, [0, Math.min(dur - 10, 24)], [0, 1], { extrapolateRight: "clamp" })} size={420} color={style.accent} />
        <div style={{ fontSize: 190, fontWeight: 900, color: style.accent, letterSpacing: -6, lineHeight: 1, textShadow: "0 10px 40px rgba(0,0,0,0.5)" }}>
          {beat.prefix ?? ""}
          {shown}
          {beat.suffix ?? ""}
        </div>
        <div style={{ fontSize: 50, fontWeight: 800, color: "#fff", marginTop: 8, textShadow: "0 4px 16px rgba(0,0,0,0.6)" }}>{beat.text}</div>
      </div>
    </AbsoluteFill>
  );
};

/** Full-screen motion scene: the speaker is covered, their voice keeps going. */
const Cutaway: React.FC<{ text: string; sub?: string; icon?: string; style: Style; dur: number }> = ({ text, sub, icon, style, dur }) => {
  const { frame, fps, enter, exit } = useEnvelope(dur);
  const wipe = interpolate(enter, [0, 1], [100, 0]);
  const words = text.split(" ");
  return (
    <AbsoluteFill style={{ clipPath: `inset(0 0 ${wipe}% 0)`, opacity: exit }}>
      <AbsoluteFill style={{ background: style.ink }} />
      {/* moving grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${style.accent}22 2px, transparent 2px), linear-gradient(90deg, ${style.accent}22 2px, transparent 2px)`,
          backgroundSize: "90px 90px",
          backgroundPosition: `0 ${frame * 1.5}px`,
        }}
      />
      {/* flat accent bars sliding in from the sides (no glow: the teardown's AI-tell scan bans halos) */}
      <div style={{ position: "absolute", left: 0, top: 560, height: 26, width: `${interpolate(enter, [0, 1], [0, 62])}%`, background: style.accent }} />
      <div style={{ position: "absolute", right: 0, top: 1340, height: 26, width: `${interpolate(enter, [0, 1], [0, 44])}%`, background: "#ffffff" }} />
      <Rings color={style.accent} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 90 }}>
        {icon ? (
          <div style={{ marginBottom: 40 }}>
            <DrawIcon name={icon} size={220} color={style.accent} delay={4} strokeWidth={1.8} />
          </div>
        ) : null}
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 24px", fontFamily: fontFamily(style.font) }}>
          {words.map((w, i) => {
            const p = spring({ frame: frame - 6 - i * 4, fps, config: { damping: 12, stiffness: 200 } });
            return (
              <span
                key={i}
                style={{
                  fontSize: 120,
                  fontWeight: 900,
                  letterSpacing: -3,
                  lineHeight: 1.05,
                  color: i % 2 ? style.accent : "#fff",
                  opacity: p,
                  transform: `translateY(${interpolate(p, [0, 1], [70, 0])}px)`,
                  display: "inline-block",
                }}
              >
                {w}
              </span>
            );
          })}
        </div>
        {sub ? (
          <div
            style={{
              marginTop: 40,
              fontFamily: fontFamily(style.font),
              fontSize: 48,
              fontWeight: 600,
              color: "#ffffffcc",
              opacity: interpolate(frame, [14, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          >
            {sub}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** "A vs B": two words face off. */
const Versus: React.FC<{ a: string; b: string; style: Style; dur: number }> = ({ a, b, style, dur }) => {
  const { frame, fps, exit } = useEnvelope(dur);
  const pa = spring({ frame, fps, config: { damping: 13, stiffness: 200 } });
  const pb = spring({ frame: frame - 6, fps, config: { damping: 13, stiffness: 200 } });
  const pv = spring({ frame: frame - 10, fps, config: { damping: 9, stiffness: 260 } });
  const card = (text: string, p: number, dir: number, bg: string, fg: string) => (
    <div
      style={{
        fontFamily: fontFamily(style.font),
        fontWeight: 900,
        fontSize: 70,
        textTransform: "uppercase",
        background: bg,
        color: fg,
        padding: "20px 34px",
        borderRadius: 24,
        transform: `translateX(${interpolate(p, [0, 1], [dir * 300, 0])}px)`,
        opacity: p,
      }}
    >
      {text}
    </div>
  );
  return (
    <AbsoluteFill style={{ ...slot(style, 240), opacity: exit }}>
      <div style={{ display: "flex", alignItems: "center", gap: 26 }}>
        {card(a, pa, -1, "#FFFFFF", style.ink)}
        <div style={{ fontFamily: fontFamily(style.font), fontWeight: 900, fontSize: 56, color: style.accent, transform: `scale(${pv})`, textShadow: "0 4px 0 rgba(0,0,0,0.5)" }}>
          VS
        </div>
        {card(b, pb, 1, style.accent, style.ink)}
      </div>
    </AbsoluteFill>
  );
};

/** A short spoken line as a big quote card. */
const Quote: React.FC<{ text: string; style: Style; dur: number }> = ({ text, style, dur }) => {
  const { enter, exit } = useEnvelope(dur);
  return (
    <AbsoluteFill style={{ ...slot(style, 200), opacity: exit }}>
      <div
        style={{
          width: 860,
          padding: "34px 44px 38px",
          background: "#FFFFFF",
          borderRadius: 30,
          borderLeft: `18px solid ${style.accent}`,
          transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px) rotate(${interpolate(enter, [0, 1], [2, -1])}deg)`,
          opacity: enter,
          fontFamily: fontFamily(style.font),
        }}
      >
        <div style={{ fontSize: 90, lineHeight: 0.6, color: style.accent, fontWeight: 900 }}>“</div>
        <div style={{ fontSize: 58, lineHeight: 1.12, fontWeight: 800, color: style.ink, textTransform: "uppercase", letterSpacing: -1 }}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};

/** B-roll cutaway: a silent clip fills the frame while the voice keeps going. */
const BRoll: React.FC<{ src: string; dur: number }> = ({ src, dur }) => {
  const frame = useCurrentFrame();
  const zoom = interpolate(frame, [0, dur], [1.08, 1.0]);
  const fade = interpolate(frame, [0, 4, dur - 4, dur], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ opacity: fade, transform: `scale(${zoom})` }}>
      <Video src={staticFile(src)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </AbsoluteFill>
  );
};

/** A screenshot in a floating app window that springs up when it's mentioned. */
const Screen: React.FC<{ src: string; label: string; style: Style; dur: number }> = ({ src, label, style, dur }) => {
  const { frame, fps, exit } = useEnvelope(dur);
  const p = spring({ frame, fps, config: { damping: 12, stiffness: 170, mass: 0.8 } });
  const float = Math.sin(frame / 14) * 6;
  return (
    <AbsoluteFill style={{ ...slot(style, 170), opacity: exit }}>
      <div style={{ width: 800, borderRadius: 26, overflow: "hidden", background: "#FFFFFF", boxShadow: "0 40px 90px rgba(0,0,0,0.45)",
                    transform: `translateY(${interpolate(p, [0, 1], [260, 0]) + float}px) rotate(${interpolate(p, [0, 1], [6, -1.5])}deg) scale(${interpolate(p, [0, 1], [0.8, 1])})`,
                    opacity: p }}>
        <div style={{ height: 54, background: "#ECECEC", display: "flex", alignItems: "center", gap: 10, padding: "0 20px" }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => <span key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c }} />)}
          <span style={{ marginLeft: 14, fontFamily: fontFamily(style.font), fontWeight: 800, fontSize: 24, color: "#333", textTransform: "uppercase", letterSpacing: 1 }}>{label}</span>
        </div>
        <Img src={staticFile(src)} style={{ width: "100%", display: "block", maxHeight: 640, objectFit: "cover", objectPosition: "top" }} />
      </div>
    </AbsoluteFill>
  );
};

/** Rep counter: a badge whose number ticks up on every rep (times measured from the motion rhythm). */
const Reps: React.FC<{ at: number[]; start: number; style: Style }> = ({ at, start, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const done = at.filter((x) => x <= t).length;
  if (!done) return null;
  const since = frame - Math.round(at[done - 1] * fps);
  const pop = spring({ frame: since, fps, config: { damping: 9, stiffness: 300, mass: 0.5 } });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "flex-end", padding: "560px 60px 0 0" }}>
      <div style={{ width: 210, height: 210, borderRadius: 105, background: style.accent, display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center", boxShadow: "0 16px 40px rgba(0,0,0,0.4)",
                    transform: `scale(${interpolate(pop, [0, 1], [1.25, 1])})` }}>
        <div style={{ fontFamily: fontFamily(style.font), fontWeight: 900, fontSize: 30, color: style.ink, letterSpacing: 3 }}>REP</div>
        <div style={{ fontFamily: fontFamily(style.font), fontWeight: 900, fontSize: 100, lineHeight: 0.95, color: "#FFFFFF" }}>{start + done}</div>
      </div>
    </AbsoluteFill>
  );
};

/** Slow-motion replay: a tag, a ring drawing round the middle of the move, a soft vignette. */
const Replay: React.FC<{ style: Style; dur: number }> = ({ style, dur }) => {
  const frame = useCurrentFrame();
  const draw = interpolate(frame, [4, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const c = 2 * Math.PI * 300;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ boxShadow: "inset 0 0 220px rgba(0,0,0,0.65)" }} />
      <svg width={1080} height={1920} style={{ position: "absolute" }}>
        <ellipse cx={540} cy={1060} rx={330} ry={420} fill="none" stroke={style.accent} strokeWidth={10} strokeLinecap="round"
                 strokeDasharray={c * 1.25} strokeDashoffset={c * 1.25 * (1 - draw)} transform="rotate(-80 540 1060)" />
      </svg>
      <div style={{ position: "absolute", top: 300, left: 70, display: "flex", alignItems: "center", gap: 14,
                    fontFamily: fontFamily(style.font), fontWeight: 900, fontSize: 44, color: "#fff", letterSpacing: 4 }}>
        <span style={{ width: 22, height: 22, borderRadius: 11, background: style.accent, opacity: Math.floor(frame / 10) % 2 ? 0.3 : 1 }} />
        SLOW-MO
      </div>
    </AbsoluteFill>
  );
};

export const BeatView: React.FC<{ beat: Beat; style: Style; dur: number }> = ({ beat, style, dur }) => {
  switch (beat.type) {
    case "hook":
      return <Hook text={beat.text} style={style} dur={dur} />;
    case "keyword":
      return <Keyword text={beat.text} icon={beat.icon} style={style} dur={dur} />;
    case "list":
      return <List text={beat.text} items={beat.items} at={beat.at} style={style} dur={dur} />;
    case "stat":
      return <Stat beat={beat} style={style} dur={dur} />;
    case "cutaway":
      return <Cutaway text={beat.text} sub={beat.sub} icon={beat.icon} style={style} dur={dur} />;
    case "versus":
      return <Versus a={beat.a} b={beat.b} style={style} dur={dur} />;
    case "quote":
      return <Quote text={beat.text} style={style} dur={dur} />;
    case "broll":
      return <BRoll src={beat.src} dur={dur} />;
    case "replay":
      return <Replay style={style} dur={dur} />;
    case "reps":
      return <Reps at={beat.at} start={beat.start} style={style} />;
    case "screen":
      return <Screen src={beat.src} label={beat.text} style={style} dur={dur} />;
  }
};
