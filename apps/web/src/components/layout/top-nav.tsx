'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, Bell, HelpCircle, Sparkles, Moon, Sun, Monitor, Menu, Palette, Droplets, Layers, Circle } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useAuthStore, useUIStore } from '@/stores';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/* ── Color interpolation helpers ── */
type RGB = [number, number, number];

const LIGHT_FAMILY_WHITES_OFFWHITES: RGB[] = [
  /* Brancos e off-whites (expandido) */
  [255, 255, 255],   // #FFFFFF
  [255, 255, 254],   // #FFFFFE
  [255, 255, 253],   // #FFFFFD
  [255, 255, 252],   // #FFFFFC
  [255, 255, 250],   // #FFFFFA
  [255, 254, 252],   // #FFFEFC
  [255, 254, 250],   // #FFFEFA
  [255, 254, 248],   // #FFFEF8
  [254, 254, 252],   // #FEFEFC
  [254, 254, 251],   // #FEFEFB
  [254, 253, 251],   // #FEFDFB
  [254, 253, 250],   // #FEFDFA
  [254, 252, 249],   // #FEFCF9
  [253, 252, 250],   // #FDFCFA
  [253, 252, 249],   // #FDFCF9
  [253, 251, 249],   // #FDFBF9
  [253, 251, 248],   // #FDFBF8
  [252, 251, 249],   // #FCFBF9
  [252, 250, 248],   // #FCFAF8
  [252, 250, 247],   // #FCFAF7
  [251, 250, 248],   // #FBFAF8
  [251, 249, 247],   // #FBF9F7
  [251, 249, 246],   // #FBF9F6
  [250, 249, 247],   // #FAF9F7
  [250, 248, 246],   // #FAF8F6
  [249, 248, 246],   // #F9F8F6
  [249, 247, 245],   // #F9F7F5
  [248, 247, 245],   // #F8F7F5
  [247, 246, 244],   // #F7F6F4
  [246, 245, 243],   // #F6F5F3
];

const LIGHT_FAMILY_COOL_OFFWHITE_GRAY: RGB[] = [
  /* Neutros frios / cinzas azulados */
  [249, 250, 252],   // #F9FAFC
  [248, 251, 255],   // #F8FBFF
  [247, 250, 253],   // #F7FAFD
  [247, 248, 250],   // #F7F8FA
  [246, 250, 255],   // #F6FAFF
  [245, 248, 253],   // #F5F8FD
  [245, 245, 245],   // #F5F5F5
  [244, 247, 251],   // #F4F7FB
  [244, 245, 248],   // #F4F5F8
  [243, 246, 250],   // #F3F6FA
  [243, 243, 243],   // #F3F3F3
  [242, 248, 255],   // #F2F8FF
  [242, 247, 252],   // #F2F7FC
  [241, 244, 248],   // #F1F4F8
  [241, 241, 241],   // #F1F1F1
  [240, 244, 252],   // #F0F4FC
  [240, 240, 240],   // #F0F0F0
  [239, 243, 249],   // #EFF3F9
  [239, 241, 244],   // #EFF1F4
  [238, 242, 247],   // #EEF2F7
  [236, 240, 246],   // #ECF0F6
  [233, 236, 240],   // #E9ECF0
  [228, 228, 228],   // #E4E4E4
  [220, 220, 220],   // #DCDCDC
  [212, 212, 212],   // #D4D4D4
  [205, 205, 205],   // #CDCDCD
];

const LIGHT_FAMILY_WARM_CREAM_SAND: RGB[] = [
  /* Off-white quente / creme / bege / areia */
  [255, 255, 240],   // #FFFFF0
  [255, 253, 244],   // #FFFDF4
  [255, 252, 246],   // #FFFCF6
  [254, 250, 242],   // #FEFAF2
  [253, 249, 241],   // #FDF9F1
  [252, 250, 246],   // #FCFAF6
  [252, 247, 238],   // #FCF7EE
  [251, 245, 236],   // #FBF5EC
  [250, 248, 245],   // #FAF8F5
  [250, 247, 240],   // #FAF7F0
  [250, 247, 233],   // #FAF7E9
  [250, 244, 234],   // #FAF4EA
  [249, 244, 232],   // #F9F4E8
  [249, 242, 230],   // #F9F2E6
  [248, 242, 238],   // #F8F2EE
  [248, 240, 226],   // #F8F0E2
  [248, 240, 218],   // #F8F0DA
  [247, 238, 222],   // #F7EEDE
  [246, 236, 218],   // #F6ECDA
  [245, 234, 214],   // #F5EAD6
  [244, 232, 210],   // #F4E8D2
  [243, 237, 224],   // #F3EDE0
  [242, 234, 238],   // #F2EAEE
  [242, 230, 206],   // #F2E6CE
  [241, 228, 202],   // #F1E4CA
  [240, 234, 214],   // #F0EAD6
  [240, 232, 208],   // #F0E8D0
  [238, 236, 234],   // #EEECEA
  [235, 228, 200],   // #EBE4C8
  [234, 229, 224],   // #EAE5E0
  [228, 220, 190],   // #E4DCBE
  [222, 212, 180],   // #DED4B4
  [216, 206, 172],   // #D8CEAC
];

const LIGHT_FAMILY_ROSE: RGB[] = [
  /* Rosa claro / blush */
  [255, 250, 253],   // #FFFAFD
  [255, 248, 252],   // #FFF8FC
  [255, 246, 251],   // #FFF6FB
  [254, 246, 251],   // #FEF6FB
  [255, 242, 248],   // #FFF2F8
  [255, 240, 245],   // #FFF0F5
  [252, 239, 247],   // #FCEFF7
  [250, 232, 240],   // #FAE8F0
  [248, 230, 241],   // #F8E6F1
  [244, 224, 234],   // #F4E0EA
  [236, 214, 226],   // #ECD6E2
];

const LIGHT_FAMILY_PEACH_YELLOW: RGB[] = [
  /* Pessego e amarelos claros */
  [255, 251, 246],   // #FFFBF6
  [255, 249, 242],   // #FFF9F2
  [255, 247, 238],   // #FFF7EE
  [255, 245, 232],   // #FFF5E8
  [255, 243, 224],   // #FFF3E0
  [255, 250, 230],   // #FFFAE6
  [255, 248, 220],   // #FFF8DC
  [255, 246, 210],   // #FFF6D2
  [254, 244, 204],   // #FEF4CC
  [252, 240, 198],   // #FCF0C6
];

const LIGHT_FAMILY_GREEN: RGB[] = [
  /* Verdes claros */
  [250, 255, 252],   // #FAFFFC
  [248, 255, 251],   // #F8FFFB
  [248, 254, 250],   // #F8FEFA
  [245, 254, 249],   // #F5FEF9
  [244, 252, 248],   // #F4FCF8
  [242, 252, 247],   // #F2FCF7
  [240, 248, 244],   // #F0F8F4
  [238, 250, 244],   // #EEFAF4
  [236, 240, 234],   // #ECF0EA
  [234, 245, 240],   // #EAF5F0
  [232, 247, 239],   // #E8F7EF
  [230, 242, 238],   // #E6F2EE
  [226, 243, 233],   // #E2F3E9
  [224, 238, 228],   // #E0EEE4
  [218, 234, 224],   // #DAEAE0
  [214, 230, 220],   // #D6E6DC
  [208, 226, 214],   // #D0E2D6
  [200, 220, 208],   // #C8DCD0
  [192, 214, 200],   // #C0D6C8
];

const LIGHT_FAMILY_AQUA_CYAN: RGB[] = [
  /* Aqua e cianos claros */
  [246, 255, 255],   // #F6FFFF
  [242, 254, 255],   // #F2FEFF
  [238, 252, 255],   // #EEFCFF
  [234, 249, 255],   // #EAF9FF
  [230, 246, 255],   // #E6F6FF
  [226, 244, 255],   // #E2F4FF
  [222, 241, 252],   // #DEF1FC
  [216, 238, 249],   // #D8EEF9
  [210, 234, 245],   // #D2EAF5
];

const LIGHT_FAMILY_BLUE_LAVENDER: RGB[] = [
  /* Frios: off-white frio, azul claro e lavanda */
  [245, 248, 255],   // #F5F8FF
  [242, 248, 255],   // #F2F8FF
  [241, 244, 248],   // #F1F4F8
  [240, 236, 244],   // #F0ECF4
  [238, 240, 248],   // #EEF0F8
  [236, 245, 255],   // #ECF5FF
  [230, 240, 252],   // #E6F0FC
  [232, 236, 246],   // #E8ECF6
  [224, 232, 244],   // #E0E8F4
  [218, 226, 240],   // #DAE2F0
  [210, 222, 238],   // #D2DEEE
];

const LIGHT_STOPS_RAW: RGB[] = [
  ...LIGHT_FAMILY_WHITES_OFFWHITES,
  ...LIGHT_FAMILY_COOL_OFFWHITE_GRAY,
  ...LIGHT_FAMILY_WARM_CREAM_SAND,
  ...LIGHT_FAMILY_ROSE,
  ...LIGHT_FAMILY_PEACH_YELLOW,
  ...LIGHT_FAMILY_GREEN,
  ...LIGHT_FAMILY_AQUA_CYAN,
  ...LIGHT_FAMILY_BLUE_LAVENDER,
];

function luminance([r, g, b]: RGB): number {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Keep the same palette entries, but enforce a smooth light-theme ramp.
const LIGHT_STOPS: RGB[] = [...LIGHT_STOPS_RAW].sort((a, b) => {
  const lum = luminance(a) - luminance(b);
  if (lum !== 0) return lum;
  const sum = (a[0] + a[1] + a[2]) - (b[0] + b[1] + b[2]);
  if (sum !== 0) return sum;
  if (a[0] !== b[0]) return a[0] - b[0];
  if (a[1] !== b[1]) return a[1] - b[1];
  return a[2] - b[2];
});

const DARK_STOPS: RGB[] = [
  /* ── Neutros (preto → cinza) ── */
  [0, 0, 0],         // preto total                    (L≈0)
  [1, 1, 1],         // preto absoluto+                (L≈1)
  [2, 2, 2],         // preto carvão profundo          (L≈2)
  [3, 3, 3],         // preto carvão+                  (L≈3)
  [4, 4, 4],         // preto denso                    (L≈4)
  [5, 5, 5],         // preto denso+                   (L≈5)
  [6, 6, 6],         // near-black                     (L≈6)
  [7, 7, 7],         // near-black+                    (L≈7)
  [8, 8, 8],         // preto profundo (#080808)       (L≈8)
  [9, 9, 9],         // preto profundo+                (L≈9)
  [10, 10, 10],      // preto grafite                  (L≈10)
  [11, 11, 11],      // preto grafite+                (L≈11)
  [12, 12, 12],      // preto fumaça                   (L≈12)
  [14, 14, 14],      // preto ônix (#0E0E0E)           (L≈14)
  [16, 16, 16],      // preto mineral                  (L≈16)
  [18, 18, 18],      // cinza carbono                 (L≈18)
  [15, 17, 21],      // grafite azulado (#0F1115)      (L≈17)
  [20, 20, 20],      // cinza neutro escuro (#141414)  (L≈20)
  [22, 22, 22],      // cinza neutro+                 (L≈22)
  [24, 24, 24],      // cinza neutro médio (#181818)   (L≈24)
  [26, 26, 26],      // cinza médio escuro            (L≈26)
  [28, 28, 28],      // preto suave (#1C1C1C)          (L≈28)
  [30, 30, 30],      // grafite suave                 (L≈30)
  [33, 33, 33],      // cinza noite (#212121)           (L≈33)
  [36, 36, 36],      // cinza noite+                  (L≈36)
  [38, 38, 38],      // preto carvão (#262626)         (L≈38)
  [42, 42, 42],      // ardósia escura                (L≈42)
  [44, 44, 44],      // cinza ardósia (#2C2C2C)        (L≈44)
  [46, 46, 46],      // cinza ardósia+                (L≈46)
  [50, 50, 50],      // grafite (#323232)              (L≈50)
  [54, 54, 54],      // grafite claro                 (L≈54)
  [58, 58, 58],      // cinza chumbo (#3A3A3A)         (L≈58)
  /* ── Quentes / Warm (marrom escuro → âmbar → areia noturna) ── */
  [22, 18, 12],      // marrom muito escuro (#16120C)  (L≈18)
  [24, 20, 14],      // marrom espresso claro          (L≈20)
  [26, 22, 15],      // espresso profundo (#1A160F)    (L≈22)
  [28, 24, 18],      // espresso médio                 (L≈24)
  [30, 26, 20],      // warm dark / marrom (#1E1A14)   (L≈27)
  [32, 26, 18],      // marrom cacau                   (L≈28)
  [33, 28, 18],      // café escuro (#211C12)          (L≈29)
  [36, 30, 20],      // cobre café                     (L≈31)
  [35, 30, 22],      // marrom médio (#231E16)         (L≈31)
  [38, 32, 24],      // cobre escuro (#262018)         (L≈33)
  [40, 33, 23],      // cobre tostado                  (L≈34)
  [42, 34, 22],      // marrom chocolate (#2A2216)     (L≈35)
  [44, 38, 28],      // areia noturna (#2C261C)        (L≈37)
  [46, 39, 27],      // âmbar tostado                  (L≈38)
  [45, 38, 26],      // âmbar noite (#2D261A)          (L≈39)
  [48, 40, 28],      // marrom quente (#30281C)        (L≈41)
  [50, 44, 32],      // creme escuro (#322C20)         (L≈43)
  [52, 42, 30],      // caramelo escuro (#342A1E)      (L≈44)
  [54, 46, 34],      // caramelo quente                (L≈46)
  [55, 45, 32],      // marrom claro (#372D20)         (L≈47)
  [58, 50, 36],      // areia tostada escura (#3A3224) (L≈50)
  [60, 52, 38],      // areia quente escura            (L≈52)
  [62, 54, 40],      // bege noturno (#3E3628)         (L≈54)
  /* ── Rosa / Rosé escuro ── */
  [24, 12, 16],      // rose shadow                    (L≈16)
  [28, 14, 20],      // rosa escuro (#1C0E14)          (L≈19)
  [30, 16, 22],      // rosé escuro suave              (L≈21)
  [34, 18, 24],      // rosé quente (#221218)          (L≈23)
  [36, 19, 27],      // rosé vinho                     (L≈25)
  [38, 20, 28],      // rosa noite (#26141C)           (L≈26)
  [40, 22, 30],      // rosé ameixa                    (L≈28)
  [42, 24, 32],      // rosé profundo (#2A1820)        (L≈30)
  [45, 26, 35],      // rosé profundo+                 (L≈33)
  [48, 28, 38],      // rosa intenso (#301C26)         (L≈35)
  [52, 32, 42],      // rosa granada                   (L≈40)
  /* ── Verdes / Forest-Teal ── */
  [2, 8, 4],         // verde abismo (#020804)         (L≈5)
  [3, 10, 5],        // verde abismo+                  (L≈6)
  [4, 12, 6],        // verde meia-noite (#040C06)     (L≈8)
  [5, 14, 8],        // verde meia-noite+              (L≈9)
  [6, 16, 10],       // floresta negra (#06100A)       (L≈11)
  [7, 17, 11],       // floresta densa                 (L≈12)
  [8, 18, 12],       // pinho escuro (#08120C)         (L≈14)
  [9, 20, 14],       // pinho profundo                 (L≈15)
  [11, 24, 17],      // musgo profundo                 (L≈19)
  [12, 22, 16],      // forest dark (#0C1610)          (L≈18)
  [10, 26, 18],      // musgo noite (#0A1A12)          (L≈20)
  [15, 30, 20],      // teal floresta                  (L≈24)
  [14, 28, 24],      // teal escuro (#0E1C18)          (L≈23)
  [16, 32, 22],      // esmeralda escuro (#102016)     (L≈26)
  [17, 34, 26],      // esmeralda musgo                (L≈28)
  [18, 35, 30],      // petrol profundo (#12231E)      (L≈29)
  [20, 38, 28],      // jade profundo (#14261C)        (L≈32)
  [22, 40, 32],      // jade noite                     (L≈34)
  [24, 42, 34],      // verde-escuro quente (#182A22)  (L≈36)
  [26, 46, 36],      // oliva floresta                 (L≈38)
  [28, 48, 38],      // oliva noturno (#1C3026)        (L≈40)
  /* ── Frios / Navy (slate → cinza frio) ── */
  [0, 1, 3],         // black navy absoluto (#000103)  (L≈1)
  [0, 1, 4],         // black navy denso               (L≈2)
  [0, 1, 6],         // black navy profundo (#000106)  (L≈2)
  [0, 2, 8],         // black navy profundo+           (L≈3)
  [0, 1, 9],         // black navy denso (#000109)     (L≈3)
  [0, 2, 12],        // navy abismo (#00020C)          (L≈3)
  [1, 3, 14],        // navy sombra                    (L≈4)
  [1, 4, 18],        // navy meia-noite (#010412)      (L≈5)
  [2, 5, 20],        // navy fechado                   (L≈6)
  [1, 5, 21],        // navy eclipse (#010515)         (L≈6)
  [2, 6, 23],        // slate-950 navy (#020617)       (L≈7)
  [3, 8, 26],        // slate-950+                      (L≈9)
  [4, 9, 30],        // navy-930                       (L≈11)
  [7, 10, 28],       // navy profundo (#070A1C)        (L≈11)
  [10, 15, 36],      // navy carvão                    (L≈16)
  [15, 23, 42],      // slate-900 navy (#0F172A)       (L≈23)
  [18, 27, 46],      // slate-900+                     (L≈27)
  [20, 32, 52],      // navy médio (#142034)           (L≈31)
  [24, 36, 55],      // navy médio+                    (L≈35)
  [30, 41, 59],      // slate-800 navy (#1E293B)       (L≈40)
  [36, 47, 65],      // slate-700 navy                 (L≈46)
  [50, 52, 60],      // cinza frio (#34343C)           (L≈52)
  [58, 60, 70],      // cinza chumbo frio              (L≈60)
  [65, 68, 80],      // cinza claro (#414450)          (L≈68)
];

function lerpRGB(a: RGB, b: RGB, t: number): RGB {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

function toHex(n: number): string {
  return n.toString(16).padStart(2, '0');
}

/** Interpolate across N evenly-spaced stops */
function sampleStops(t: number, stops: RGB[]): RGB {
  const segments = stops.length - 1;
  const seg = Math.min(Math.floor(t * segments), segments - 1);
  const local = t * segments - seg;
  return lerpRGB(stops[seg], stops[seg + 1], local);
}

function tintToColor(tint: number, stops: RGB[]): string {
  const rgb = sampleStops(tint / 100, stops);
  return `#${toHex(rgb[0])}${toHex(rgb[1])}${toHex(rgb[2])}`;
}

function buildGradientTrack(stops: RGB[], steps = 16, direction = 'to right'): string {
  const colors: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const rgb = sampleStops(i / steps, stops);
    colors.push(`#${toHex(rgb[0])}${toHex(rgb[1])}${toHex(rgb[2])}`);
  }
  return `linear-gradient(${direction}, ${colors.join(', ')})`;
}

/** Convert hex to HSL tuple [h, s%, l%] */
function hexToHsl(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return [
    Math.round(h * 360 * 10) / 10,
    Math.round(s * 1000) / 10,
    Math.round(l * 1000) / 10,
  ];
}

/**
 * Derive CSS custom property overrides from a tint color for dark/light mode.
 * Returns HSL strings in Tailwind format "H S% L%" (no commas, no hsl wrapper).
 */
function deriveTintTokens(tintHex: string, dark: boolean) {
  const [h, s, l] = hexToHsl(tintHex);
  if (dark) {
    return {
      '--background': `${h} ${s}% ${l}%`,
      '--card': `${h} ${s}% ${Math.min(l + 4, 25)}%`,
      '--card-blended': `${h} ${Math.min(s + 4, 100)}% ${Math.min(l + 10, 34)}%`,
      '--card-inset': `${h} ${s}% ${Math.max(l - 3, 2)}%`,
      '--muted': `${h} ${Math.max(s - 5, 0)}% ${Math.min(l + 9, 30)}%`,
      '--border': `${h} ${Math.max(s - 10, 0)}% ${Math.min(l + 14, 35)}%`,
      '--border-blended': `${h} ${Math.max(s - 4, 0)}% ${Math.min(l + 22, 46)}%`,
      '--border-inset': `${h} ${Math.max(s - 8, 0)}% ${Math.max(l - 1, 3)}%`,
      '--accent': `${h} ${Math.max(s - 5, 0)}% ${Math.min(l + 9, 30)}%`,
    };
  }
  return {
    '--background': `${h} ${s}% ${l}%`,
    '--card': `${h} ${Math.max(s - 5, 0)}% ${Math.min(l + 3, 100)}%`,
    '--card-blended': `${h} ${Math.max(s - 2, 0)}% ${Math.min(l + 6, 100)}%`,
    '--card-inset': `${h} ${Math.min(s + 3, 100)}% ${Math.max(l - 8, 80)}%`,
    '--muted': `${h} ${s}% ${Math.max(l - 4, 88)}%`,
    '--border': `${h} ${Math.max(s - 10, 0)}% ${Math.max(l - 12, 78)}%`,
    '--border-blended': `${h} ${Math.max(s - 6, 0)}% ${Math.max(l - 8, 80)}%`,
    '--border-inset': `${h} ${Math.max(s - 5, 0)}% ${Math.max(l - 16, 72)}%`,
    '--accent': `${h} ${s}% ${Math.max(l - 4, 88)}%`,
  };
}

/** Mix two hex colors in JS (replaces CSS color-mix for cross-browser compat) */
function mixHex(colorA: string, colorB: string, weightA: number): string {
  const parse = (hex: string): RGB => {
    const h = hex.replace('#', '').padEnd(6, '0').slice(0, 6);
    const v = parseInt(h, 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  };
  const a = parse(colorA);
  const b = parse(colorB);
  const w = Math.max(0, Math.min(1, weightA));
  return `#${toHex(Math.round(a[0] * w + b[0] * (1 - w)))}${toHex(Math.round(a[1] * w + b[1] * (1 - w)))}${toHex(Math.round(a[2] * w + b[2] * (1 - w)))}`;
}

/** Exported for use by ask page, layout and sidebar */
export { tintToColor, buildGradientTrack, hexToHsl, deriveTintTokens, mixHex, LIGHT_STOPS, DARK_STOPS };

export function TopNav() {
  const { user } = useAuthStore();
  const { sidebarState, toggleSidebar, chatBgTintLight, chatBgTintDark, setChatBgTintLight, setChatBgTintDark, syncSidebarTheme, tintMode, cycleTintMode } = useUIStore();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const firstName = user?.name?.split(' ')[0] ?? 'Usuário';

  const lightGradientH = useMemo(() => buildGradientTrack(LIGHT_STOPS), []);
  const darkGradientH = useMemo(() => buildGradientTrack(DARK_STOPS), []);

  const activeTint = isDark ? chatBgTintDark : chatBgTintLight;
  const setActiveTint = isDark ? setChatBgTintDark : setChatBgTintLight;
  const activeGradient = isDark ? darkGradientH : lightGradientH;
  const [tintLensActive, setTintLensActive] = useState(false);
  const tintLensPos = Math.min(96, Math.max(4, activeTint));
  const tintLensColor = useMemo(
    () => tintToColor(activeTint, isDark ? DARK_STOPS : LIGHT_STOPS),
    [activeTint, isDark],
  );
  const TintModeIcon =
    tintMode === 'layered'
      ? Layers
      : tintMode === 'blended'
        ? Palette
        : tintMode === 'inset'
          ? Droplets
          : Circle;

  const handleTintChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setActiveTint(Number(e.target.value)),
    [setActiveTint],
  );

  const [tintOpen, setTintOpen] = useState(false);
  const tintRef = useRef<HTMLDivElement>(null);

  // 3-state cycle: dark → light → system → dark
  const handleThemeToggle = useCallback(() => {
    const map: Record<string, 'light' | 'dark' | 'system'> = {
      dark: 'light',
      light: 'system',
      system: 'dark',
    };
    const next = map[theme ?? 'system'] ?? 'dark';
    setTheme(next);
    const effectiveTheme = next === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : next;
    syncSidebarTheme(effectiveTheme);
  }, [theme, setTheme, syncSidebarTheme]);

  const handleTintToggle = useCallback(() => {
    setTintOpen((prev) => !prev);
  }, []);

  // Close tint bar on click outside
  useEffect(() => {
    if (!tintOpen) return;
    const handler = (e: MouseEvent) => {
      if (tintRef.current && !tintRef.current.contains(e.target as Node)) {
        setTintOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [tintOpen]);

  return (
    <header className="sticky top-0 z-40 h-14 flex-none border-b border-border/60 bg-background/80 backdrop-blur-xl">
      <div className="flex h-full items-center justify-between gap-4 px-4 md:px-6">
        {/* Left: Menu toggle (mobile) */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card shadow-sm transition hover:bg-accent"
            onClick={toggleSidebar}
            aria-label="Alternar menu"
            aria-controls="dashboard-sidebar"
            aria-expanded={sidebarState !== 'hidden'}
          >
            <Menu className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        {/* Center: Search */}
        <div className="relative flex-1 max-w-lg">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="h-9 w-full rounded-lg border-border bg-muted/50 pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus-visible:border-indigo-300 focus-visible:ring-1 focus-visible:ring-indigo-500/50"
            placeholder="Buscar documentos, legislação..."
          />
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5">
          {/* Theme toggle (3-state: dark → light → system) */}
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={handleThemeToggle}
            title={
              theme === 'dark' ? 'Modo escuro (clique → claro)'
              : theme === 'light' ? 'Modo claro (clique → automático)'
              : 'Automático (clique → escuro)'
            }
          >
            {theme === 'dark' ? (
              <Moon className="h-4 w-4" />
            ) : theme === 'light' ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Monitor className="h-4 w-4" />
            )}
          </Button>

          {/* Tint palette toggle + bar */}
          <div ref={tintRef} className="relative">
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-9 w-9 rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground',
                tintOpen && 'bg-accent text-foreground',
              )}
              onClick={handleTintToggle}
              aria-label="Ajustar tom do fundo"
              title="Ajustar tom do fundo"
            >
              <Palette className="h-4 w-4" />
            </Button>
            {/* Tint bar — revealed on click, positioned to the left */}
            <div
              className={cn(
                'absolute right-full top-1/2 z-50 -translate-y-1/2 pr-2 transition-opacity duration-200',
                tintOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0',
              )}
            >
              <div className="flex items-center gap-1.5">
                {/* Tint mode cycle: layered → blended → inset → uniform */}
                <button
                  type="button"
                  onClick={cycleTintMode}
                  className={cn(
                    'flex h-7 w-7 items-center justify-center rounded-full border transition-colors',
                    tintMode === 'uniform'
                      ? 'border-indigo-400 bg-indigo-500/20 text-indigo-500'
                      : tintMode === 'inset'
                        ? 'border-emerald-400 bg-emerald-500/20 text-emerald-500'
                        : tintMode === 'blended'
                          ? 'border-amber-400 bg-amber-500/20 text-amber-500'
                          : 'border-border/50 bg-background/80 text-muted-foreground hover:text-foreground',
                  )}
                  aria-label="Modo de cor"
                  title={
                    tintMode === 'layered'
                      ? 'Camadas: input/canvas branco (clique → mesclado)'
                      : tintMode === 'blended'
                        ? 'Mesclado: input/canvas claro (clique → profundo)'
                        : tintMode === 'inset'
                          ? 'Profundo: input/canvas mais escuro (clique → uniforme)'
                          : 'Uniforme: mesma cor (clique → camadas)'
                  }
                >
                  <TintModeIcon className="h-3.5 w-3.5" />
                </button>
                {/* Gradient bar */}
                <div className="relative w-48 rounded-full border border-border/50 shadow-md backdrop-blur-md">
                  <div
                    className={cn(
                      'pointer-events-none absolute -top-12 z-10 transition-opacity duration-150',
                      tintLensActive ? 'opacity-100' : 'opacity-0',
                    )}
                    style={{ left: `${tintLensPos}%`, transform: 'translateX(-50%)' }}
                  >
                    <div
                      className="relative h-9 w-9 rounded-full border border-border/70 shadow-lg ring-2 ring-background/85"
                      style={{
                        background: activeGradient,
                        backgroundSize: '240% 100%',
                        backgroundPosition: `${activeTint}% 50%`,
                      }}
                    >
                      <span
                        className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80"
                        style={{ backgroundColor: tintLensColor }}
                      />
                    </div>
                    <div className="mx-auto h-3 w-px bg-border/70" />
                  </div>
                  <div
                    className="h-4 w-full rounded-full"
                    style={{ background: activeGradient }}
                  />
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={activeTint}
                    onChange={handleTintChange}
                    onMouseEnter={() => setTintLensActive(true)}
                    onMouseLeave={() => setTintLensActive(false)}
                    onFocus={() => setTintLensActive(true)}
                    onBlur={() => setTintLensActive(false)}
                    onPointerDown={() => setTintLensActive(true)}
                    className="chat-tint-slider absolute inset-0 h-4 w-full cursor-pointer appearance-none bg-transparent"
                    aria-label="Ajustar tom do fundo"
                  />
                </div>
              </div>
            </div>
          </div>

          <IconButton icon={Sparkles} label="Insights da IA" />
          <IconButton icon={HelpCircle} label="Central de ajuda" />
          <IconButton icon={Bell} label="Notificações" indicator />

          {/* User Avatar */}
          <div className="ml-1 flex items-center gap-2 rounded-lg border border-border bg-card px-2 py-1 shadow-sm">
            <div className="h-7 w-7 rounded-full bg-indigo-100 text-center text-sm font-semibold leading-7 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
              {firstName.charAt(0).toUpperCase()}
            </div>
            <span className="hidden text-sm font-medium text-foreground md:inline">{firstName}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

interface IconButtonProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  indicator?: boolean;
}

function IconButton({ icon: Icon, label, indicator }: IconButtonProps) {
  return (
    <button
      type="button"
      className="relative flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-label={label}
      title={label}
    >
      <Icon className="h-4 w-4" />
      {indicator && (
        <span
          className={cn(
            'absolute right-1.5 top-1.5 h-2 w-2 rounded-full',
            'bg-rose-500 animate-pulse'
          )}
        />
      )}
    </button>
  );
}
