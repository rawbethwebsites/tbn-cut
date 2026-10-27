import { Audio, Video } from "@remotion/media";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import React from "react";
import {
  AbsoluteFill,
  CalculateMetadataFunction,
  Composition,
  Img,
  Easing,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Captions } from "./Captions";
import { Style, Word } from "./types";

const anton = loadAnton("normal", { weights: ["400"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["700", "800", "900"], subsets: ["latin"] });
const DISPLAY = anton.fontFamily;
const UI = inter.fontFamily;

/** One scene of the explainer: what Qwen planned, timed to the spoken sentences. */
export type Scene = {
  kind: "hook" | "statement" | "chart" | "tracker" | "list" | "versus" | "stat" | "end" | "typeon" | "window";
  s: number;
  e: number;
  theme: "dark" | "cream";
  label?: string; // small chip above the title, e.g. "A VISITOR ASKED ME"
  title: string;
  accent?: string; // word(s) of the title painted in the accent colour
  sub?: string; // line under the title
  box?: string; // red box line under the title
  chart?: { type: "wave_vs_steps" | "up" | "down" | "bars"; a?: string; b?: string; values?: number[]; labels?: string[] };
  rows?: string[]; // tracker rows (habits)
  items?: string[]; // list items
  left?: string;
  right?: string;
  value?: number;
  unit?: string;
  cta?: string;
  bg?: string; // background picture (file in the job folder), dimmed behind the scene
  media?: string; // "window" scenes: a picture or screen recording (file in the job folder) shown in a desktop window
  status?: string; // gauge stats: a line that ticks in when the needle settles, e.g. "FIRST MONTH"
  at?: number[]; // seconds (from scene start) when each item/row is said
};

export type ExplainerProps = {
  video: string;
  fps: number;
  durationInFrames: number;
  words: Word[];
  scenes: Scene[];
  series: string; // "GIST & GRIND"
  episode: string; // "EP 03"
  handle: string; // "@rawbeth"
  accent: string;
  sfx: boolean;
  palette?: Partial<typeof BASE>; // brand colours (TBN: navy, cream, green)
  logoOnDark?: string; // logo file in public/ for dark scenes; builds in at the start, assembles on the end card
  logoOnCream?: string;
  captionStyle?: Style; // Rob's locked caption look instead of the small boxed captions
  motion?: MotionPack; // motion template (templates/motion/*.json): titles, numbers, transitions, backdrop, windows
};

import { Gauge, GenieWindow, Grid, MaskRise, MotionPack, Shutter } from "./OsMotion";

const BASE = { dark: "#141414", cream: "#F1EDE4", ink: "#111111", grey: "#8A8A8A", sub_dark: "#BDBDBD", sub_cream: "#555555" };
// Set once per frame from props (ExplainerEdit), read by every scene below.
let C = { ...BASE };

/** The logo builds itself: its four quarters fly in one after another and lock together. */
const LogoBuild: React.FC<{ src: string; size: number; delay?: number }> = ({ src, size, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const quarters = [
    { clip: "inset(0 50% 50% 0)", dx: -1, dy: -1 },
    { clip: "inset(0 0 50% 50%)", dx: 1, dy: -1 },
    { clip: "inset(50% 50% 0 0)", dx: -1, dy: 1 },
    { clip: "inset(50% 0 0 50%)", dx: 1, dy: 1 },
  ];
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      {quarters.map((q, i) => {
        const k = spring({ frame: frame - delay - i * 4, fps, config: { damping: 13, stiffness: 170, mass: 0.7 } });
        const off = interpolate(k, [0, 1], [size * 0.6, 0]);
        return (
          <Img key={i} src={staticFile(src)} style={{ position: "absolute", inset: 0, width: size, height: size, clipPath: q.clip,
            opacity: Math.min(1, k * 1.4), transform: `translate(${q.dx * off}px, ${q.dy * off}px) rotate(${interpolate(k, [0, 1], [q.dx * 25, 0])}deg)` }} />
        );
      })}
    </div>
  );
};

const useIn = (delay = 0, stiffness = 200) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping: 14, stiffness, mass: 0.7 } });
};

/** Big condensed title; the accent words go red, words land one after another. */
const Title: React.FC<{ text: string; accent?: string; size: number; color: string; accentColor: string; delay?: number; align?: "left" | "center" }> = ({
  text,
  accent,
  size,
  color,
  accentColor,
  delay = 0,
  align = "left",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const marks = new Set((accent ?? "").toUpperCase().split(/\s+/).filter(Boolean));
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: `0 ${size * 0.22}px`, justifyContent: align === "center" ? "center" : "flex-start" }}>
      {words.map((w, i) => {
        const p = spring({ frame: frame - delay - i * 2.5, fps, config: { damping: 13, stiffness: 240, mass: 0.6 } });
        const bare = w.replace(/[^A-Z0-9']/g, "");
        return (
          <span
            key={i}
            style={{
              fontFamily: DISPLAY,
              fontSize: size,
              lineHeight: 0.98,
              color: marks.has(bare) ? accentColor : color,
              opacity: p,
              transform: `translateY(${interpolate(p, [0, 1], [size * 0.35, 0])}px)`,
              display: "inline-block",
            }}
          >
            {w}
          </span>
        );
      })}
    </div>
  );
};

const Chip: React.FC<{ text: string; bg: string; fg: string; size?: number }> = ({ text, bg, fg, size = 30 }) => (
  <span style={{ fontFamily: UI, fontWeight: 900, fontSize: size, background: bg, color: fg, padding: "6px 14px", letterSpacing: 1, textTransform: "uppercase" }}>
    {text}
  </span>
);

/** Two lines drawing in: a wave (how you feel) against a staircase (what gets done). */
const Chart: React.FC<{ scene: Scene; ink: string; accent: string; dur: number }> = ({ scene, ink, accent, dur }) => {
  const frame = useCurrentFrame();
  const W = 920, H = 640;
  const t = interpolate(frame, [6, Math.max(20, dur * 0.7)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const ch = scene.chart ?? { type: "wave_vs_steps" };
  const wave = Array.from({ length: 60 }, (_, i) => {
    const x = (i / 59) * W;
    const y = H * 0.45 - Math.sin(i / 5.5) * H * 0.28 - Math.sin(i / 2.1) * H * 0.06;
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const steps = Array.from({ length: 9 }, (_, i) => {
    const x0 = (i / 9) * W, x1 = ((i + 1) / 9) * W, y = H * 0.92 - (i / 8) * H * 0.75;
    return `${i ? "L" : "M"}${x0.toFixed(1)},${y.toFixed(1)} L${x1.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const line = (ch.type === "down" ? -1 : 1);
  const trend = `M0,${line > 0 ? H * 0.9 : H * 0.15} C ${W * 0.35},${line > 0 ? H * 0.8 : H * 0.25} ${W * 0.6},${line > 0 ? H * 0.35 : H * 0.6} ${W},${line > 0 ? H * 0.08 : H * 0.92}`;
  const bars = ch.values?.length ? ch.values : [];
  const maxV = Math.max(1, ...bars);
  const showB = ch.type === "wave_vs_steps" && frame > dur * 0.35;
  return (
    <div style={{ marginTop: 50 }}>
      <svg width={W} height={H} style={{ overflow: "visible" }}>
        <line x1={0} y1={H} x2={W} y2={H} stroke={ink} strokeOpacity={0.25} strokeWidth={3} />
        {ch.type === "wave_vs_steps" ? (
          <>
            <path d={wave} fill="none" stroke={showB ? C.grey : ink} strokeWidth={8} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - Math.min(1, t * 1.6)} />
            {showB ? (
              <path d={steps} fill="none" stroke={accent} strokeWidth={10} strokeLinejoin="round" pathLength={1} strokeDasharray={1}
                strokeDashoffset={1 - interpolate(frame, [dur * 0.35, dur * 0.85], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
            ) : null}
          </>
        ) : ch.type === "bars" && bars.length ? (
          bars.map((v, i) => {
            const bw = W / bars.length - 30;
            const h = (v / maxV) * H * 0.9 * interpolate(frame - i * 4, [6, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            return <rect key={i} x={i * (bw + 30) + 15} y={H - h} width={bw} height={h} fill={i === bars.length - 1 ? accent : ink} />;
          })
        ) : (
          <path d={trend} fill="none" stroke={accent} strokeWidth={10} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - t} />
        )}
      </svg>
      <div style={{ display: "flex", gap: 40, marginTop: 26, fontFamily: UI, fontWeight: 800, fontSize: 28, color: ink, textTransform: "uppercase" }}>
        {ch.a ? <span><span style={{ display: "inline-block", width: 34, height: 6, background: ch.type === "wave_vs_steps" && showB ? C.grey : ink, marginRight: 10, verticalAlign: "middle" }} />{ch.a}</span> : null}
        {ch.b && (showB || ch.type !== "wave_vs_steps") ? <span><span style={{ display: "inline-block", width: 34, height: 6, background: accent, marginRight: 10, verticalAlign: "middle" }} />{ch.b}</span> : null}
      </div>
    </div>
  );
};

/** Habit tracker: rows x 7 days, boxes tick in one by one. Last box of row 1 stays empty (the day you missed). */
const Tracker: React.FC<{ scene: Scene; ink: string; accent: string; dur: number }> = ({ scene, ink, accent, dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rows = (scene.rows ?? []).slice(0, 5);
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  return (
    <div style={{ marginTop: 60, fontFamily: UI }}>
      <div style={{ display: "flex", marginLeft: 230, gap: 14, marginBottom: 10 }}>
        {days.map((d, i) => <div key={i} style={{ width: 80, textAlign: "center", fontWeight: 800, fontSize: 24, color: ink, opacity: 0.6 }}>{d}</div>)}
      </div>
      {rows.map((r, ri) => {
        const rowIn = scene.at?.[ri] !== undefined ? Math.round(scene.at[ri] * fps) : 8 + ri * Math.max(10, (dur - 20) / Math.max(1, rows.length));
        return (
          <div key={ri} style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18, opacity: interpolate(frame - rowIn, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
            <div style={{ width: 216, fontWeight: 900, fontSize: 30, color: ink, textTransform: "uppercase", lineHeight: 1.05 }}>{r}</div>
            {days.map((_, di) => {
              const on = frame - rowIn - 4 - di * 3;
              const checked = on > 0 && !(ri === 0 && di === 6);
              const p = spring({ frame: on, fps, config: { damping: 12, stiffness: 260 } });
              return (
                <div key={di} style={{ width: 84, height: 84, border: `4px solid ${checked ? accent : ink}`, background: checked ? accent : "transparent", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${checked ? interpolate(p, [0, 1], [0.6, 1]) : 1})` }}>
                  {checked ? <span style={{ color: "#fff", fontSize: 50, fontWeight: 900, lineHeight: 1 }}>✓</span> : null}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

const ListScene: React.FC<{ scene: Scene; ink: string; accent: string; dur: number }> = ({ scene, ink, accent, dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const items = (scene.items ?? []).slice(0, 6);
  return (
    <div style={{ marginTop: 50 }}>
      {items.map((it, i) => {
        const at = scene.at?.[i] !== undefined ? Math.round(scene.at[i] * fps) - 3 : 8 + i * Math.max(8, (dur - 20) / Math.max(1, items.length));
        const p = spring({ frame: frame - at, fps, config: { damping: 14, stiffness: 220 } });
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 26, marginBottom: 26, opacity: p, transform: `translateX(${interpolate(p, [0, 1], [-60, 0])}px)` }}>
            <span style={{ fontFamily: DISPLAY, fontSize: 92, color: accent, width: 90 }}>{String(i + 1).padStart(2, "0")}</span>
            <span style={{ fontFamily: DISPLAY, fontSize: 76, color: ink, lineHeight: 1 }}>{it.toUpperCase()}</span>
          </div>
        );
      })}
    </div>
  );
};

const Versus: React.FC<{ scene: Scene; ink: string; accent: string }> = ({ scene, ink, accent }) => {
  const a = useIn(4), b = useIn(12), v = useIn(18, 300);
  return (
    <div style={{ display: "flex", alignItems: "stretch", gap: 24, marginTop: 70 }}>
      <div style={{ flex: 1, border: `5px solid ${ink}`, padding: 34, opacity: a, transform: `translateX(${interpolate(a, [0, 1], [-80, 0])}px)` }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 104, color: ink, lineHeight: 1 }}>{(scene.left ?? "").toUpperCase()}</div>
      </div>
      <div style={{ alignSelf: "center", fontFamily: DISPLAY, fontSize: 70, color: accent, transform: `scale(${v})` }}>VS</div>
      <div style={{ flex: 1, background: accent, padding: 34, opacity: b, transform: `translateX(${interpolate(b, [0, 1], [80, 0])}px)` }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 104, color: "#fff", lineHeight: 1 }}>{(scene.right ?? "").toUpperCase()}</div>
      </div>
    </div>
  );
};

const Stat: React.FC<{ scene: Scene; ink: string; accent: string; dur: number }> = ({ scene, ink, accent, dur }) => {
  const frame = useCurrentFrame();
  const v = scene.value ?? 0;
  const n = interpolate(frame, [4, Math.min(dur - 6, 30)], [0, v], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <div style={{ marginTop: 40 }}>
      <div style={{ fontFamily: DISPLAY, fontSize: 300, lineHeight: 0.9, color: accent }}>
        {Number.isInteger(v) ? Math.round(n).toLocaleString() : n.toFixed(1)}
        <span style={{ fontSize: 120, color: ink }}>{scene.unit ?? ""}</span>
      </div>
    </div>
  );
};

/** Documentary type-on: a line types itself onto a screen, one word in red, slow push-in. */
const TypeOn: React.FC<{ scene: Scene; accent: string; dur: number }> = ({ scene, accent, dur }) => {
  const frame = useCurrentFrame();
  const text = scene.title.toUpperCase();
  const n = Math.floor(interpolate(frame, [6, Math.max(12, dur * 0.65)], [0, text.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const marks = new Set((scene.accent ?? "").toUpperCase().split(/\s+/).filter(Boolean));
  const push = interpolate(frame, [0, dur], [1, 1.07]);
  let k = 0;
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", transform: `scale(${push})` }}>
      <div style={{ width: 900, minHeight: 640, borderRadius: 40, background: "#0B0F0C", border: "14px solid #2A2A2A", padding: "70px 60px",
                    boxShadow: "inset 0 0 0 4px #000", position: "relative", overflow: "hidden" }}>
        <AbsoluteFill style={{ backgroundImage: "repeating-linear-gradient(0deg, rgba(255,255,255,0.05) 0 2px, transparent 2px 6px)" }} />
        <div style={{ fontFamily: "Menlo, monospace", fontWeight: 700, fontSize: 64, lineHeight: 1.25, color: "#E8E8E8", position: "relative" }}>
          {text.split(/(\s+)/).map((w, i) => {
            const start = k;
            k += w.length;
            const shown = w.slice(0, Math.max(0, n - start));
            return <span key={i} style={{ color: marks.has(w.replace(/[^A-Z0-9']/g, "")) ? accent : undefined }}>{shown}</span>;
          })}
          <span style={{ opacity: Math.floor(frame / 8) % 2 ? 0 : 1, color: accent }}>▍</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const SceneView: React.FC<{ scene: Scene; p: ExplainerProps; dur: number; first?: boolean; last?: boolean }> = ({ scene, p, dur, first = false, last = false }) => {
  const frame = useCurrentFrame();
  const m = p.motion ?? {};
  const shutter = m.transition === "shutter";
  const dark = scene.theme !== "cream";
  const ink = dark ? "#FFFFFF" : C.ink;
  const bg = dark ? C.dark : C.cream;
  const enter = shutter ? 1 : interpolate(frame, [0, 6], [0, 1], { extrapolateRight: "clamp" });
  const exit = shutter ? 1 : interpolate(frame, [dur - 5, dur], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const boxIn = useIn(10);
  const titleSize = scene.kind === "statement" || scene.kind === "end" ? 175 : scene.kind === "hook" ? 140 : 125;
  if (scene.kind === "typeon") {
    return (
      <AbsoluteFill style={{ background: C.dark, opacity: Math.min(1, enter + 0.4) }}>
        <AbsoluteFill style={{ opacity: exit }}><TypeOn scene={scene} accent={p.accent} dur={dur} /></AbsoluteFill>
        {shutter ? <Shutter dur={dur} color={C.dark} seam={p.accent} first={first} last={last} speed={m.speed} /> : null}
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ background: scene.kind === "hook" ? "transparent" : bg, opacity: Math.min(1, enter + 0.4) }}>
      {scene.bg ? (
        <AbsoluteFill style={{ transform: `scale(${interpolate(frame, [0, dur], [1.0, 1.08])})` }}>
          <Img src={staticFile(scene.bg)} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "grayscale(0.6) brightness(0.45)" }} />
        </AbsoluteFill>
      ) : null}
      {m.backdrop === "grid" && scene.kind !== "hook" ? <Grid ink={ink} /> : null}
      <AbsoluteFill style={{ padding: p.captionStyle ? "200px 80px 560px" : "200px 80px 300px", justifyContent: "center", opacity: exit }}>
        {scene.label && scene.kind !== "window" ? <div style={{ marginBottom: 22 }}><Chip text={scene.label} bg={dark ? "#FFFFFF" : C.ink} fg={dark ? C.ink : "#FFFFFF"} size={28} /></div> : null}
        {m.title === "maskrise" ? (
          <MaskRise text={scene.title} accent={scene.accent} size={scene.kind === "window" ? 100 : titleSize} color={ink} accentColor={p.accent} font={DISPLAY}
                    align={scene.kind === "statement" || scene.kind === "end" || scene.kind === "window" ? "center" : "left"} stagger={m.stagger} speed={m.speed} />
        ) : (
          <Title text={scene.title} accent={scene.accent} size={scene.kind === "window" ? 100 : titleSize} color={ink} accentColor={p.accent}
                 align={scene.kind === "statement" || scene.kind === "end" || scene.kind === "window" ? "center" : "left"} />
        )}
        {scene.sub ? (
          <div style={{ fontFamily: DISPLAY, fontSize: 70, color: dark ? C.sub_dark : C.sub_cream, marginTop: 12, textAlign: scene.kind === "statement" || scene.kind === "end" ? "center" : "left" }}>
            {scene.sub.toUpperCase()}
          </div>
        ) : null}
        {scene.box ? (
          <div style={{ display: "flex", justifyContent: scene.kind === "statement" ? "center" : "flex-start", marginTop: 30 }}>
            <div style={{ background: p.accent, color: "#fff", fontFamily: DISPLAY, fontSize: 64, padding: "14px 30px", lineHeight: 1.05, textAlign: "center", maxWidth: 860, transform: `scale(${interpolate(boxIn, [0, 1], [0.85, 1])})`, opacity: boxIn }}>
              {scene.box.toUpperCase()}
            </div>
          </div>
        ) : null}
        {scene.kind === "chart" ? <Chart scene={scene} ink={ink} accent={p.accent} dur={dur} /> : null}
        {scene.kind === "tracker" ? <Tracker scene={scene} ink={ink} accent={p.accent} dur={dur} /> : null}
        {scene.kind === "list" ? <ListScene scene={scene} ink={ink} accent={p.accent} dur={dur} /> : null}
        {scene.kind === "versus" ? <Versus scene={scene} ink={ink} accent={p.accent} /> : null}
        {scene.kind === "stat" && m.stat === "gauge" ? (
          <Gauge value={scene.value ?? 0} unit={scene.unit} status={scene.status} ink={ink} accent={p.accent} track={dark ? "#FFFFFF22" : "#00000018"} font={DISPLAY} ui={UI} speed={m.speed} />
        ) : scene.kind === "stat" ? <Stat scene={scene} ink={ink} accent={p.accent} dur={dur} /> : null}
        {scene.kind === "window" && scene.media ? (
          <GenieWindow media={scene.media} title={scene.label} dur={dur} style={m.window ?? "pop"} chrome={dark ? "#1B2550" : "#FFFFFF"} ink={ink} ui={UI} speed={m.speed} />
        ) : null}
        {scene.kind === "end" ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18, marginTop: 50, opacity: boxIn }}>
            {(dark ? p.logoOnDark : p.logoOnCream) ? <LogoBuild src={(dark ? p.logoOnDark : p.logoOnCream) as string} size={190} delay={4} /> : null}
            {scene.cta ? <Chip text={scene.cta} bg="#FFFFFF" fg={C.ink} size={40} /> : null}
            <span style={{ fontFamily: UI, fontWeight: 700, fontSize: 28, color: dark ? C.sub_dark : C.sub_cream }}>{p.handle} · {p.series}</span>
          </div>
        ) : null}
      </AbsoluteFill>
      {shutter ? <Shutter dur={dur} color={C.dark} seam={p.accent} first={first} last={last} speed={m.speed} /> : null}
    </AbsoluteFill>
  );
};

/** Boxed captions at the bottom: white caps on a dark box, the spoken word on an accent box. */
const BoxCaptions: React.FC<{ words: Word[]; accent: string }> = ({ words, accent }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const t = frame / fps;
  // pages of up to 4 words, never across a sentence end
  const pages: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    cur.push(w);
    const nx = words[i + 1];
    if (!nx || cur.length >= 4 || /[.!?]$/.test(w.w) || nx.s - w.e > 0.5) {
      pages.push(cur);
      cur = [];
    }
  });
  const page = pages.find((pg, i) => t >= pg[0].s - 0.05 && t < (pages[i + 1]?.[0].s ?? pg[pg.length - 1].e + 0.5));
  if (!page) return null;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: height * 0.86, display: "flex", justifyContent: "center" }}>
      <div style={{ background: "rgba(20,20,20,0.88)", padding: "10px 18px", borderRadius: 10, display: "flex", gap: 12 }}>
        {page.map((w, i) => {
          const active = t >= w.s - 0.02 && t < (page[i + 1]?.s ?? w.e + 0.2);
          return (
            <span key={i} style={{ fontFamily: UI, fontWeight: 900, fontSize: 40, color: "#fff", textTransform: "uppercase", background: active ? accent : "transparent", padding: "0 6px", borderRadius: 4 }}>
              {w.w.replace(/[,;:.!?]+$/, "")}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export const ExplainerEdit: React.FC<ExplainerProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const hook = p.scenes.find((s) => s.kind === "hook" && t >= s.s && t < s.e);
  C = { ...BASE, ...(p.palette ?? {}) };
  const now = p.scenes.find((s) => t >= s.s && t < s.e);
  const onCream = now ? now.theme === "cream" && now.kind !== "typeon" : false;
  return (
    <AbsoluteFill style={{ background: C.dark }}>
      {/* the real footage: its sound always plays; the picture only shows (blurred, dark) behind the hook */}
      <AbsoluteFill style={{ opacity: hook ? 1 : 0, filter: "blur(10px) brightness(0.45)", transform: "scale(1.08)" }}>
        <Video src={staticFile(p.video)} />
      </AbsoluteFill>
      {p.scenes.map((s, i) => {
        const from = Math.round(s.s * fps);
        const dur = Math.max(8, Math.round((s.e - s.s) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`${s.kind}: ${s.title}`} premountFor={fps}>
            <SceneView scene={s} p={p} dur={dur} first={i === 0} last={i === p.scenes.length - 1} />
            {p.sfx ? <Audio src={staticFile(i === 0 ? "sfx/impact.wav" : "sfx/whoosh.wav")} volume={0.4} /> : null}
            {p.sfx && s.kind === "typeon"
              ? Array.from({ length: Math.min(24, Math.floor(dur / 3)) }).map((_, k) => (
                  <Sequence key={`t${k}`} from={6 + k * 3} durationInFrames={3}>
                    <Audio src={staticFile("sfx/tick.wav")} volume={0.18} />
                  </Sequence>
                ))
              : null}
            {p.sfx && (s.kind === "tracker" || s.kind === "list")
              ? (s.at ?? []).map((a, k) => (
                  <Sequence key={k} from={Math.max(0, Math.round(a * fps))} durationInFrames={6}>
                    <Audio src={staticFile("sfx/tick.wav")} volume={0.4} />
                  </Sequence>
                ))
              : null}
          </Sequence>
        );
      })}
      {/* series tag, always on (with the logo building in first when there is one) */}
      <div style={{ position: "absolute", top: 90, left: 80, display: "flex", gap: 14, alignItems: "center" }}>
        {p.logoOnDark ? <LogoBuild src={(onCream ? p.logoOnCream : p.logoOnDark) ?? p.logoOnDark} size={64} /> : null}
        <Chip text={p.series} bg={p.accent} fg={p.palette ? C.dark : "#fff"} size={24} />
        <span style={{ fontFamily: UI, fontWeight: 900, fontSize: 24, color: "#9A9A9A" }}>{p.episode}</span>
      </div>
      {p.captionStyle ? (
        <Captions words={p.words} style={{ ...p.captionStyle, captionMode: "fixed", captionY: 0.8, accent: p.accent, text: onCream ? C.ink : "#FFFFFF" }} />
      ) : (
        <BoxCaptions words={p.words} accent={p.accent} />
      )}
    </AbsoluteFill>
  );
};

const calc: CalculateMetadataFunction<ExplainerProps> = ({ props }) => ({ durationInFrames: Math.max(1, props.durationInFrames), fps: props.fps });

export const ExplainerComposition = () => (
  <Composition
    id="TBNExplainer"
    component={ExplainerEdit}
    durationInFrames={300}
    fps={30}
    width={1080}
    height={1920}
    calculateMetadata={calc}
    defaultProps={{ video: "jobs/demo/cut.mp4", fps: 30, durationInFrames: 300, words: [], scenes: [], series: "GIST & GRIND", episode: "EP 01", handle: "@rawbeth", accent: "#D7141A", sfx: true }}
  />
);
