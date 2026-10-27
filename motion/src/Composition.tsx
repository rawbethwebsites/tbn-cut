import { Audio, Video } from "@remotion/media";
import { AbsoluteFill, CalculateMetadataFunction, Composition, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { BeatView } from "./Beats";
import { Captions } from "./Captions";
import { CutFx } from "./Motion";
import { Beat, defaultStyle, EditProps } from "./types";

const calculateMetadata: CalculateMetadataFunction<EditProps> = ({ props }) => ({
  durationInFrames: Math.max(1, props.durationInFrames),
  fps: props.fps,
});

const SFX: Record<string, string> = { reps: "", hook: "impact", keyword: "pop", stat: "pop", quote: "pop", versus: "whoosh", cutaway: "whoosh", list: "pop", broll: "whoosh", screen: "whoosh" };

/** One sound on each graphic's entrance; list items tick in as they appear. */
const Sfx: React.FC<{ beat: Beat }> = ({ beat }) => {
  const { fps } = useVideoConfig();
  const name = SFX[beat.type];
  return (
    <>
      {name ? <Audio src={staticFile(`sfx/${name}.wav`)} volume={0.45} /> : null}
      {beat.type === "list" || beat.type === "reps"
        ? (beat.at ?? []).map((t, k) => (
            <Sequence key={k} from={Math.max(0, Math.round(t * fps) - 4)} durationInFrames={6}>
              <Audio src={staticFile("sfx/tick.wav")} volume={0.4} />
            </Sequence>
          ))
        : null}
    </>
  );
};

const ProgressBar: React.FC<{ color: string }> = ({ color }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div style={{ position: "absolute", top: 0, left: 0, height: 10, width: `${(frame / durationInFrames) * 100}%`, background: color }} />
  );
};

export const TBNEdit: React.FC<EditProps> = ({ video, words, beats, style, face, cuts }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const inCutaway = beats.some((b) => b.type === "cutaway" && t >= b.s && t < b.e);
  const editorial = style.layout === "editorial";
  const beatSeq = (b: Beat, i: number) => {
    const from = Math.round(b.s * fps);
    const dur = Math.max(10, Math.round((b.e - b.s) * fps));
    return (
      <Sequence key={i} name={`${b.type}: ${b.text}`} from={from} durationInFrames={dur} premountFor={fps}>
        <AbsoluteFill style={{ textTransform: style.uppercase === false ? "none" : "uppercase" }}>
          <BeatView beat={b} style={style} dur={dur} />
        </AbsoluteFill>
        {style.sfx !== false ? <Sfx beat={b} /> : null}
      </Sequence>
    );
  };
  if (editorial) {
    const ink = style.ink ?? "#111111";
    const cur = beats.filter((b) => b.type !== "broll" && b.type !== "cutaway" && b.s <= t).length;
    const panelBusy = beats.some((b) => b.type !== "broll" && b.type !== "cutaway" && t >= b.s - 0.1 && t < b.e + 0.1);
    return (
      <AbsoluteFill style={{ background: "#F1EDE4" }}>
        {/* the speaker, framed like a magazine photo */}
        <div style={{ position: "absolute", top: 110, left: 60, right: 60, height: 1040, borderRadius: 36, overflow: "hidden", border: `4px solid ${ink}` }}>
          {/* 9:16 footage cropped to fill the card (keeps the face, which sits around 35% down) */}
          <div style={{ position: "absolute", left: 0, width: 952, height: 1692, top: -(1692 - 1032) * 0.35 }}>
            <CutFx cuts={cuts ?? []} kind={style.transition ?? "punch"}>
              <Video name="Cut" src={staticFile(video)} />
            </CutFx>
          </div>
          {beats.map((b, i) => (b.type === "broll" ? beatSeq(b, i) : null))}
        </div>
        {/* numbered panel under the card */}
        <div style={{ position: "absolute", top: 1180, left: 60, right: 60, height: 6, background: ink }} />
        <div style={{ position: "absolute", top: 1200, left: 60, right: 60, display: "flex", justifyContent: "space-between", alignItems: "center",
                      fontFamily: "Poppins, sans-serif", fontWeight: 800, fontSize: 26, letterSpacing: 3, color: ink }}>
          <span>NO. {String(Math.max(1, cur)).padStart(2, "0")}</span>
          <span style={{ width: 34, height: 34, borderRadius: 17, background: style.accent }} />
        </div>
        <div style={{ position: "absolute", top: 1250, left: 60, right: 60, height: 360 }}>
          {beats.map((b, i) => (b.type !== "broll" && b.type !== "cutaway" ? beatSeq(b, i) : null))}
        </div>
        {beats.map((b, i) => (b.type === "cutaway" ? beatSeq(b, i) : null))}
        {/* words fill the panel when no graphic is up; they drop below it while one is */}
        <Captions words={words} style={{ ...style, captionMode: "fixed", text: ink, captionSize: panelBusy ? 52 : 76,
                                         captionY: panelBusy ? 0.9 : 0.75 }} hidden={inCutaway} />
        {style.progressBar ? <ProgressBar color={style.accent} /> : null}
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ background: "black" }}>
      {/* emphasis push: the camera leans in while a key word or stat is on screen */}
      <AbsoluteFill style={{ transform: `scale(${1 + 0.06 * Math.max(0, ...beats.filter((b) => ["keyword", "stat", "quote"].includes(b.type)).map((b) =>
          t < b.s || t > b.e + 0.4 ? 0 : t < b.e ? Math.min(1, (t - b.s) / Math.max(0.5, b.e - b.s)) : 1 - (t - b.e) / 0.4))})` }}>
        <CutFx cuts={cuts ?? []} kind={style.transition ?? "punch"}>
          <Video name="Cut" src={staticFile(video)} />
        </CutFx>
      </AbsoluteFill>
      {beats.map((b, i) => {
        const from = Math.round(b.s * fps);
        const dur = Math.max(10, Math.round((b.e - b.s) * fps));
        return (
          <Sequence key={i} name={`${b.type}: ${b.text}`} from={from} durationInFrames={dur} premountFor={fps}>
            {/* graphics follow the locked caption look: all caps */}
            <AbsoluteFill style={{ textTransform: style.uppercase === false ? "none" : "uppercase" }}>
              <BeatView beat={b} style={style} dur={dur} />
            </AbsoluteFill>
            {style.sfx !== false ? <Sfx beat={b} /> : null}
          </Sequence>
        );
      })}
      <Captions
        words={words}
        style={style}
        hidden={inCutaway}
        face={face ?? undefined}
        busySide={(s0, e0) => {
          const b = beats.find((x) => x.type !== "cutaway" && x.type !== "broll" && x.s - 0.2 < e0 && x.e + 0.2 > s0);
          if (!b) return null;
          return b.type === "hook" ? "top" : style.graphicsAt === "bottom" ? "bottom" : "top";
        }}
      />
      {style.progressBar ? <ProgressBar color={style.accent} /> : null}
    </AbsoluteFill>
  );
};

export const MyComposition = () => {
  return (
    <Composition
      id="TBNEdit"
      component={TBNEdit}
      durationInFrames={300}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={calculateMetadata}
      defaultProps={{
        video: "jobs/demo/cut.mp4",
        fps: 30,
        durationInFrames: 300,
        words: [],
        beats: [],
        style: defaultStyle,
      }}
    />
  );
};
