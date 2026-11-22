// armada-flow — "The Dispatch Bench" (anatomy-style isometric figure)
// Meja tabung pneumatik: agen menitip amplop (job) ke lemari sortir (bus),
// tabung membawa kanister ke mesin host (wr-node), hasil kembali.
// Build: node art/build.mjs           → art/armada-flow.svg      (dark)
//        node art/build.mjs --light   → art/armada-flow-light.svg
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIGHT = process.argv.includes("--light");
const WIDTH = 760, HEIGHT = 470;

const BENCH = { x: -170, y: -70, w: 340, d: 140, r: 8 };
const BENCH_H = 11, FOOT_H = 7;

const RACK = { x: -152, y: 6, w: 62, d: 50, r: 3 };
const AGENTS = ["DEVIN", "HERMES", "AGY", "MEMOH"];

const BUS = { x: -46, y: -46, w: 62, d: 64, r: 3 };
const BUS_H = 60;
const DIAL_Z = BENCH_H + BUS_H + 8;

const HOSTS = [
  { name: "polywarroom", lamp: "green", y: -52 },
  { name: "cyber1", lamp: "red", y: -2 },
  { name: "laptop", lamp: "green", y: 46 },
];
const TOWER_W = 48, TOWER_D = 40, TOWER_H = 42, TOWER_X = 98;

const P = k.fitProjection(
  [...k.boxCorners(BENCH, -FOOT_H, BENCH_H + 84), [0, 0, -FOOT_H - 2]],
  WIDTH, HEIGHT, { pad: 24, azimuth: 45 });

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const Dt = (points, style) => k.dotsSvg(points, style);
const T = (m, text, o) => k.faceTextSvg(m, text, o);
const topText = (at, z, text, o = {}) =>
  T(k.topMatrix(at, z, P, "x"), text, { size: 4.4, tone: "mid", ...o });
const sideText = ([x, y, z], text, o = {}) => {
  const [sx, sy] = at([x, y, z]);
  return `<text class="iso-face-text" data-tone="${o.tone || "mid"}" x="${sx.toFixed(1)}" y="${sy.toFixed(1)}" font-size="${o.size || 3.4}" text-anchor="${o.anchor || "middle"}">${text}</text>`;
};

// ---------- meja ----------
function bench() {
  const out = [`<path class="iso-halo" d="${k.haloOf(BENCH, -FOOT_H, BENCH_H, P)}"/>`];
  for (const [x, y] of k.corners(BENCH, 20)) {
    out.push(S(k.cylinder(x, y, 8, -FOOT_H, 2, P, 24), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.6, -FOOT_H + 2, FOOT_H - 2, P, 24), { tone: "mid" }));
  }
  out.push(S(k.slabOf(BENCH, 0, BENCH_H, P, 8, 1.4), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(BENCH, 6), BENCH_H, P), { tone: "faint" }));
  const screws = k.corners(BENCH, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.1, BENCH_H, P, 14)).join(""), { tone: "lo" }));
  out.push(Dt(screws.map(([x, y]) => at([x, y, BENCH_H])), { size: 0.5 }));
  const strip = { x: BENCH.x + 24, y: BENCH.y + BENCH.d - 15, w: 190, d: 8, r: 1.5 };
  out.push(S(k.slabOf(strip, BENCH_H, 0.8, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 5, strip.x + strip.w - 5, 5, 6,
    strip.y + 1, BENCH_H + 0.8, [2, 3.4], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(T(k.topMatrix([strip.x + strip.w / 2, strip.y + 4.6], BENCH_H + 0.8, P, "x"),
    "ARMADA — by MaximaLabs", { size: 5.4, tone: "hi", anchor: "middle" }));
  return out.join("");
}

// ---------- rak agen: 4 kantong surat berdiri ----------
function agentRack() {
  const out = [];
  const baseH = BENCH_H + 3;
  out.push(S(k.slabOf(RACK, BENCH_H, 3, P, 3, 0.4), { tone: "mid" }));
  const slotD = (RACK.d - 8) / AGENTS.length;
  AGENTS.forEach((name, i) => {
    const cy = RACK.y + 4 + slotD * i + slotD / 2;
    // amplop berdiri di dalam kantong: slab tipis vertikal (pakai sisi tinggi)
    const env = { x: RACK.x + 6, y: cy - slotD * 0.32, w: 34, d: slotD * 0.64, r: 0.8 };
    const envH = 16 + (i % 2) * 3;
    out.push(S(k.slabOf(env, baseH, envH, P, 2, 0.35), { tone: "hi", crease: "lo", lit: true }));
    // lipatan segitiga di muka atas amplop
    out.push(L(k.lineOnTop([env.x + 2, env.y + env.d / 2], [env.x + env.w / 2, env.y + env.d - 1.5], baseH + envH, P)
      + k.lineOnTop([env.x + env.w / 2, env.y + env.d - 1.5], [env.x + env.w - 2, env.y + env.d / 2], baseH + envH, P), { tone: "lo" }));
    out.push(topText([env.x + env.w / 2, cy + 0.5], baseH + envH + 0.2, name,
      { size: 3.4, anchor: "middle", tone: "mid" }));
    // dinding kantong antar slot
    const wy = RACK.y + 4 + slotD * i;
    out.push(S(k.slabOf({ x: RACK.x + 4, y: wy - 0.7, w: 42, d: 1.4, r: 0.5 }, baseH, 10, P, 2), { tone: "mid" }));
  });
  const wyEnd = RACK.y + 4 + slotD * AGENTS.length;
  out.push(S(k.slabOf({ x: RACK.x + 4, y: wyEnd - 0.7, w: 42, d: 1.4, r: 0.5 }, baseH, 10, P, 2), { tone: "mid" }));
  // rel penahan depan rendah
  out.push(S(k.slabOf({ x: RACK.x + 4, y: RACK.y + 4, w: 42, d: 1.6, r: 0.6 }, baseH, 5, P, 2), { tone: "mid" }));
  // panah alur: rak → bus
  const a0 = at([RACK.x + RACK.w + 2, RACK.y + 4, BENCH_H + 9]);
  const a1 = at([BUS.x - 2, BUS.y + BUS.d - 6, BENCH_H + 9]);
  out.push(L(k.pathOf([a0, a1]), { tone: "mid", flow: true }));
  out.push(sideText([(RACK.x + BUS.x) / 2 + 4, RACK.y + 2, BENCH_H + 13], "job", { size: 3.6, tone: "mid" }));
  return out.join("");
}

// ---------- lemari sortir (bus) ----------
function sorter() {
  const out = [];
  out.push(S(k.slabOf(BUS, BENCH_H, BUS_H, P, 4, 0.9), { tone: "mid" }));
  out.push(S(k.slabOf(k.insetPlan(BUS, -2), BENCH_H + BUS_H, 3, P, 4, 0.5), { tone: "hi" }));
  const fx = BUS.x + 7, fz0 = BENCH_H + 11, cw = 15, ch = 14, gx = 3, gz = 6;
  const yf = BUS.y + BUS.d;
  for (let r = 0; r < 2; r++)
    for (let c = 0; c < 3; c++) {
      const x0 = fx + c * (cw + gx), z0 = fz0 + r * (ch + gz);
      const pts = [[x0, yf, z0], [x0 + cw, yf, z0], [x0 + cw, yf, z0 + ch], [x0, yf, z0 + ch]].map(at);
      out.push(L(k.pathOf(pts, true), { tone: "lo" }));
      const inner = [[x0 + 1.5, yf - 0.5, z0 + 1.5], [x0 + cw - 1.5, yf - 0.5, z0 + 1.5], [x0 + cw - 1.5, yf - 0.5, z0 + ch - 4]].map(at);
      out.push(L(k.pathOf(inner), { tone: "faint" }));
    }
  for (const c of [0, 1]) {
    const x0 = fx + c * (cw + gx) + 2.5, z0 = fz0 + 3;
    const pts = [[x0, yf + 0.4, z0], [x0 + cw - 5, yf + 0.4, z0], [x0 + cw - 5, yf + 0.4, z0 + 8], [x0, yf + 0.4, z0 + 8]].map(at);
    out.push(L(k.pathOf(pts, true), { tone: "hi" }));
  }
  // dial antrian
  const [dx, dy] = [BUS.x + 15, BUS.y + 15];
  out.push(S(k.cylinder(dx, dy, 2.6, BENCH_H + BUS_H + 3, 6, P, 20), { tone: "mid" }));
  out.push(S(k.cylinder(dx, dy, 9, DIAL_Z, 5, P, 48, 0.7), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(dx, dy, 9, DIAL_Z + 3, DIAL_Z + 5, 56, P, 0.3), { tone: "lo" }));
  const tk = k.radialTicks(dx, dy, 7.6, 24, 4, DIAL_Z + 5, [1.1, 2.2], P);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  out.push(L(k.lineOnTop([dx, dy], [dx + 5.4, dy - 4], DIAL_Z + 5.3, P), { tone: "lit" }));
  out.push(L(k.ring(dx, dy, 1.5, DIAL_Z + 5.3, P, 16), { tone: "mid" }));
  out.push(T(k.topMatrix([dx, dy + 5.8], DIAL_Z + 5.3, P, "x"), "queue", { size: 2.6, tone: "lo", anchor: "middle" }));
  // lampu + nama
  const lx = BUS.x + BUS.w - 14, ly = BUS.y + 14;
  out.push(S(k.cylinder(lx, ly, 1.6, BENCH_H + BUS_H + 3, 7, P, 14), { tone: "mid" }));
  out.push(S(k.cylinder(lx, ly, 3.4, BENCH_H + BUS_H + 10, 3, P, 24), { tone: "hi", crease: "lo", lit: true }));
  out.push(L(k.ring(lx, ly, 2.2, BENCH_H + BUS_H + 13.2, P, 20), { tone: "green" }));
  out.push(topText([BUS.x + BUS.w / 2 + 6, BUS.y + BUS.d - 10], BENCH_H + BUS_H + 3.2,
    "BUS · mailbox", { size: 4.2, anchor: "middle", tone: "hi" }));
  // port tabung sisi kanan
  for (const [i] of HOSTS.entries()) {
    const py = BUS.y + 16 + i * 16;
    out.push(S(k.cylinder(BUS.x + BUS.w - 4, py, 4.4, BENCH_H + BUS_H - 16, 8, P, 20), { tone: "mid" }));
  }
  return out.join("");
}

// ---------- tabung ----------
function tubes() {
  const out = [];
  const zT = BENCH_H + BUS_H - 11;
  HOSTS.forEach((h, i) => {
    const py = BUS.y + 16 + i * 16;
    const ty = h.y + TOWER_D / 2;
    const x1 = TOWER_X + TOWER_W / 2;
    const x0 = BUS.x + BUS.w - 4;
    const seg = (a, b, r = 2.0) =>
      out.push(`<path class="iso-line" data-tone="hi" d="${k.pathOf([at(a), at(b)])}" style="stroke-width:${r * 1.6}"/>`);
    const elbowP = [x1, py, zT];
    seg([x0, py, zT], elbowP);
    out.push(S(k.cylinder(x1, py, 3.1, zT - 3, 6, P, 18), { tone: "mid" }));
    if (Math.abs(ty - py) > 2) {
      seg(elbowP, [x1, ty, zT]);
      out.push(S(k.cylinder(x1, ty, 3.1, zT - 3, 6, P, 18), { tone: "mid" }));
    }
    // turun vertikal ke atas menara
    seg([x1, ty, zT], [x1, ty, BENCH_H + TOWER_H + 7]);
    out.push(S(k.cylinder(x1, ty, 3.4, BENCH_H + TOWER_H + 4, 4, P, 18), { tone: "mid" }));
  });
  // kanister di tabung pertama
  const cx = BUS.x + BUS.w + 24, cy = BUS.y + 16, cz = zT;
  out.push(S(k.cylinder(cx, cy, 2.4, cz - 1.2, 2.4, P, 16), { tone: "hi", lit: true }));
  out.push(S(k.cylinder(cx - 4.5, cy, 2.0, cz - 1.0, 2.0, P, 16), { tone: "mid" }));
  out.push(S(k.cylinder(cx + 4.5, cy, 2.0, cz - 1.0, 2.0, P, 16), { tone: "mid" }));
  return out.join("");
}

// ---------- menara host ----------
function tower(h) {
  const out = [];
  const t = { x: TOWER_X, y: h.y, w: TOWER_W, d: TOWER_D, r: 3 };
  for (const [x, y] of k.corners(t, 7))
    out.push(S(k.cylinder(x, y, 4.4, BENCH_H, 2.4, P, 18), { tone: "lo" }));
  out.push(S(k.slabOf(t, BENCH_H + 2.4, TOWER_H, P, 4, 0.8), { tone: "mid" }));
  const yf = h.y + TOWER_D;
  const vents = [];
  for (let r = 0; r < 5; r++) {
    const z = BENCH_H + 12 + r * 5;
    vents.push(k.pathOf([at([t.x + 6, yf + 0.3, z]), at([t.x + t.w - 6, yf + 0.3, z])]));
  }
  out.push(L(vents.join(""), { tone: "faint" }));
  const plate = { x: t.x + 6, y: h.y + TOWER_D - 9, w: TOWER_W - 12, d: 7, r: 1 };
  out.push(S(k.slabOf(plate, BENCH_H + TOWER_H + 0.4, 0.8, P, 2), { tone: "lo", crease: "none" }));
  out.push(topText([plate.x + plate.w / 2, plate.y + plate.d / 2 + 0.6], BENCH_H + TOWER_H + 1.3,
    h.name, { size: h.name.length > 8 ? 3.2 : 4, anchor: "middle", tone: "hi" }));
  const hx = t.x + 12, hy = h.y + 10;
  out.push(S(k.cylinder(hx, hy, 5.6, BENCH_H + TOWER_H + 0.6, 2.6, P, 36, 0.5), { tone: "hi", crease: "lo" }));
  const tk = k.radialTicks(hx, hy, 4.6, 12, 4, BENCH_H + TOWER_H + 3.2, [0.8, 1.6], P);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  out.push(L(k.lineOnTop([hx, hy], [hx + 2.8, hy - 2.4], BENCH_H + TOWER_H + 3.4, P), { tone: "lit" }));
  const lx = t.x + TOWER_W - 12, ly = h.y + 10;
  out.push(S(k.cylinder(lx, ly, 3.2, BENCH_H + TOWER_H + 0.6, 2.4, P, 20), { tone: "hi", lit: true }));
  out.push(L(k.ring(lx, ly, 2.1, BENCH_H + TOWER_H + 3.1, P, 18), { tone: h.lamp }));
  out.push(Dt([at([t.x + TOWER_W - 12, h.y + TOWER_D - 6, BENCH_H + TOWER_H + 1])], { size: 0.55, tone: "hi" }));
  out.push(topText([t.x + t.w / 2, h.y + TOWER_D / 2], BENCH_H + TOWER_H + 1.2, "wr-node",
    { size: 2.8, anchor: "middle", tone: "faint" }));
  return out.join("");
}

const body = [bench(), agentRack(), sorter(), tubes(), ...HOSTS.map(tower)];

const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT,
  standalone: true,
  className: LIGHT ? " light" : "",
  label:
    "Armada by MaximaLabs: meja tabung pneumatik. Empat agen (Devin, Hermes, agy, memoh) menitip amplop job di rak kiri; lemari sortir bus di tengah mengantri job; tabung membawa kanister ke tiga menara host — polywarroom dan laptop hijau, cyber1 merah — tempat daemon wr-node mengeksekusi dan mengembalikan hasil.",
  body,
});

const file = LIGHT ? "armada-flow-light.svg" : "armada-flow.svg";
// tema light: injeksikan override data-theme="light" pada svg standalone
const themed = LIGHT ? svg.replace('data-theme="true"', 'data-theme="light"') : svg;
writeFileSync(join(HERE, file), themed);
console.log("wrote", file, themed.length, "bytes");
