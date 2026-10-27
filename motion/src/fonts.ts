import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadPoppins } from "@remotion/google-fonts/Poppins";

const montserrat = loadMontserrat("normal", { weights: ["600", "800", "900"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["600", "800", "900"], subsets: ["latin"] });
const poppins = loadPoppins("normal", { weights: ["600", "800", "900"], subsets: ["latin"] });

export const fontFamily = (name: string) =>
  name === "Inter" ? inter.fontFamily : name === "Poppins" ? poppins.fontFamily : montserrat.fontFamily;
