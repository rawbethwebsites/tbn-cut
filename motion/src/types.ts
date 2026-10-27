export type Word = { w: string; s: number; e: number };

export type Beat =
  | { type: "hook"; s: number; e: number; text: string }
  | { type: "keyword"; s: number; e: number; text: string; icon?: string }
  | { type: "list"; s: number; e: number; text: string; items: string[]; at?: number[] }
  | { type: "stat"; s: number; e: number; text: string; value: number; prefix?: string; suffix?: string }
  | { type: "cutaway"; s: number; e: number; text: string; sub?: string; icon?: string }
  | { type: "versus"; s: number; e: number; text: string; a: string; b: string }
  | { type: "quote"; s: number; e: number; text: string }
  | { type: "broll"; s: number; e: number; text: string; src: string }
  | { type: "screen"; s: number; e: number; text: string; src: string }
  | { type: "reps"; s: number; e: number; text: string; at: number[]; start: number }
  | { type: "replay"; s: number; e: number; text: string };

export type Style = {
  accent: string;
  ink: string;
  font: "Montserrat" | "Inter" | "Poppins";
  captionSize: number;
  captionY: number; // 0-1 from top, centre of the caption block
  maxWords: number;
  progressBar: boolean;
  uppercase?: boolean;
  text?: string; // caption colour (spoken word uses accent)
  sfx?: boolean;
  transition?: "punch" | "whip" | "none"; // effect on every cut // a pop / whoosh / impact on each graphic (default on)
  graphicsAt?: "top" | "bottom" | "panel";
  layout?: "full" | "editorial"; // editorial = face in a card on a cream page, graphics in a numbered panel // where card graphics sit; captions take the other side
  captionMode?: "move" | "fixed"; // move = TBN house (jumps around the face), fixed = one spot
};

export type EditProps = {
  video: string; // file inside public/
  fps: number;
  durationInFrames: number;
  words: Word[];
  beats: Beat[];
  style: Style;
  face?: { top: number; bottom: number } | null;
  cuts?: number[]; // seconds where one cut ends and the next begins // band the speaker's face fills (0-1 of height)
};

export const defaultStyle: Style = {
  accent: "#EA6113",
  ink: "#0B0B0B",
  font: "Poppins",
  captionSize: 70,
  captionY: 0.76,
  maxWords: 5,
  progressBar: true,
};
