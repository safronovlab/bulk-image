/**
 * colorMath.js — pure utility module for hex parsing, RGB <-> LAB conversion,
 * and Delta-E 2000 distance. Used by preview.worker.js and React components.
 *
 *
 * No default export. No side effects. No third-party color libraries.
 */

/**
 * @typedef {[number, number, number]} RgbTriple
 * @typedef {[number, number, number]} LabTriple
 */

const HEX_CHARSET = /^[0-9A-Fa-f]+$/;

// D65 reference white tristimulus values (CIE 1931, 2-degree observer).
const Xn = 95.047;
const Yn = 100.0;
const Zn = 108.883;

/**
 * Parse a hex color string to an RGB triple.
 * Accepts "#RRGGBB", "RRGGBB", "#RGB", "RGB". Trims surrounding whitespace.
 * Rejects 4 / 8 char (RGBA) hex; alpha is preserved bit-perfectly elsewhere.
 *
 * @param {string} hex
 * @returns {RgbTriple} [r, g, b], each 0..255
 * @throws {RangeError} if input is not a valid hex
 */
export function parseHex(hex) {
  if (typeof hex !== 'string') {
    throw new RangeError(`Invalid hex: ${hex}`);
  }
  const trimmed = hex.trim();
  if (trimmed === '') {
    throw new RangeError('Invalid hex: empty string');
  }
  const body = trimmed.startsWith('#') ? trimmed.slice(1) : trimmed;
  if (!HEX_CHARSET.test(body)) {
    throw new RangeError(`Invalid hex: ${hex}`);
  }
  let normalized;
  if (body.length === 3) {
    normalized = body
      .split('')
      .map((c) => c + c)
      .join('');
  } else if (body.length === 6) {
    normalized = body;
  } else {
    throw new RangeError(`Invalid hex length: ${hex}`);
  }
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return [r, g, b];
}

/**
 * Convert an RGB triple to "#RRGGBB" uppercase.
 *
 * @param {RgbTriple} rgb
 * @returns {string}
 * @throws {RangeError} if any channel is out of [0, 255]
 */
export function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length !== 3) {
    throw new RangeError(`Invalid RGB: ${rgb}`);
  }
  const [r, g, b] = rgb;
  for (const c of [r, g, b]) {
    if (typeof c !== 'number' || !Number.isFinite(c) || c < 0 || c > 255) {
      throw new RangeError(`RGB channel out of range: ${c}`);
    }
  }
  // Use Math.round to mirror backend `np.round + .astype(uint8)`.
  const toHex = (n) => Math.round(n).toString(16).padStart(2, '0').toUpperCase();
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/**
 * Shallow validator for hex strings; never throws.
 *
 * @param {string} s
 * @returns {boolean}
 */
export function isValidHex(s) {
  if (typeof s !== 'string') return false;
  const trimmed = s.trim();
  if (trimmed === '') return false;
  const body = trimmed.startsWith('#') ? trimmed.slice(1) : trimmed;
  if (!HEX_CHARSET.test(body)) return false;
  return body.length === 3 || body.length === 6;
}

/**
 * Expand "#FFF" to "#FFFFFF", uppercase. Throws on invalid input.
 *
 * @param {string} s
 * @returns {string}
 * @throws {RangeError}
 */
export function normalizeHex(s) {
  const rgb = parseHex(s);
  return rgbToHex(rgb);
}

/**
 * sRGB companding: gamma-corrected sRGB channel -> linear-light value.
 * @param {number} c — channel in [0, 1]
 */
function srgbToLinear(c) {
  return c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92;
}

/** Inverse companding. */
function linearToSrgb(c) {
  return c > 0.0031308 ? 1.055 * Math.pow(c, 1 / 2.4) - 0.055 : 12.92 * c;
}

/**
 * Convert sRGB (0..255) to CIELAB via D65 reference white.
 *
 * @param {RgbTriple} rgb
 * @returns {LabTriple} [L, a, b]
 */
export function rgbToLab(rgb) {
  const [r8, g8, b8] = rgb;
  const r = srgbToLinear(r8 / 255);
  const g = srgbToLinear(g8 / 255);
  const b = srgbToLinear(b8 / 255);

  // sRGB D65 -> XYZ matrix (CIE).
  const X = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) * 100;
  const Y = (r * 0.2126729 + g * 0.7151522 + b * 0.072175) * 100;
  const Z = (r * 0.0193339 + g * 0.119192 + b * 0.9503041) * 100;

  const fx = labF(X / Xn);
  const fy = labF(Y / Yn);
  const fz = labF(Z / Zn);

  const L = 116 * fy - 16;
  const a = 500 * (fx - fy);
  const bb = 200 * (fy - fz);
  return [L, a, bb];
}

function labF(t) {
  const delta = 6 / 29;
  return t > delta * delta * delta
    ? Math.cbrt(t)
    : t / (3 * delta * delta) + 4 / 29;
}

function labFInv(t) {
  const delta = 6 / 29;
  return t > delta
    ? t * t * t
    : 3 * delta * delta * (t - 4 / 29);
}

/**
 * Convert CIELAB to sRGB (0..255), clamped to integers.
 *
 * @param {LabTriple} lab
 * @returns {RgbTriple}
 */
export function labToRgb(lab) {
  const [L, a, b] = lab;
  const fy = (L + 16) / 116;
  const fx = a / 500 + fy;
  const fz = fy - b / 200;
  const X = Xn * labFInv(fx);
  const Y = Yn * labFInv(fy);
  const Z = Zn * labFInv(fz);

  // XYZ -> linear sRGB
  const xn = X / 100;
  const yn = Y / 100;
  const zn = Z / 100;
  const rl = xn * 3.2404542 + yn * -1.5371385 + zn * -0.4985314;
  const gl = xn * -0.969266 + yn * 1.8760108 + zn * 0.041556;
  const bl = xn * 0.0556434 + yn * -0.2040259 + zn * 1.0572252;

  const r = linearToSrgb(rl) * 255;
  const g = linearToSrgb(gl) * 255;
  const bb = linearToSrgb(bl) * 255;

  // Clamp to [0, 255] and round (gamut clipping; out-of-gamut LABs flatten).
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
  return [clamp(r), clamp(g), clamp(bb)];
}

/**
 * CIEDE2000 distance between two LAB triples (Sharma et al. 2005).
 * Symmetric, non-negative. kL = kC = kH = 1.
 *
 * @param {LabTriple} labA
 * @param {LabTriple} labB
 * @returns {number}
 */
export function deltaE2000(labA, labB) {
  if (
    labA[0] === labB[0] &&
    labA[1] === labB[1] &&
    labA[2] === labB[2]
  ) {
    return 0;
  }
  const [L1, a1, b1] = labA;
  const [L2, a2, b2] = labB;

  const C1 = Math.sqrt(a1 * a1 + b1 * b1);
  const C2 = Math.sqrt(a2 * a2 + b2 * b2);
  const Cbar = (C1 + C2) / 2;

  const Cbar7 = Math.pow(Cbar, 7);
  const G = 0.5 * (1 - Math.sqrt(Cbar7 / (Cbar7 + Math.pow(25, 7))));

  const a1p = (1 + G) * a1;
  const a2p = (1 + G) * a2;

  const C1p = Math.sqrt(a1p * a1p + b1 * b1);
  const C2p = Math.sqrt(a2p * a2p + b2 * b2);

  const h1p = hueAngleDeg(b1, a1p);
  const h2p = hueAngleDeg(b2, a2p);

  const dLp = L2 - L1;
  const dCp = C2p - C1p;

  let dhp;
  if (C1p * C2p === 0) {
    dhp = 0;
  } else {
    const diff = h2p - h1p;
    if (Math.abs(diff) <= 180) {
      dhp = diff;
    } else if (diff > 180) {
      dhp = diff - 360;
    } else {
      dhp = diff + 360;
    }
  }
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin(degToRad(dhp / 2));

  const Lbarp = (L1 + L2) / 2;
  const Cbarp = (C1p + C2p) / 2;

  let hbarp;
  if (C1p * C2p === 0) {
    hbarp = h1p + h2p;
  } else {
    const sum = h1p + h2p;
    if (Math.abs(h1p - h2p) <= 180) {
      hbarp = sum / 2;
    } else if (sum < 360) {
      hbarp = (sum + 360) / 2;
    } else {
      hbarp = (sum - 360) / 2;
    }
  }

  const T =
    1 -
    0.17 * Math.cos(degToRad(hbarp - 30)) +
    0.24 * Math.cos(degToRad(2 * hbarp)) +
    0.32 * Math.cos(degToRad(3 * hbarp + 6)) -
    0.2 * Math.cos(degToRad(4 * hbarp - 63));

  const dTheta = 30 * Math.exp(-Math.pow((hbarp - 275) / 25, 2));
  const Cbarp7 = Math.pow(Cbarp, 7);
  const Rc = 2 * Math.sqrt(Cbarp7 / (Cbarp7 + Math.pow(25, 7)));
  const Sl =
    1 +
    (0.015 * Math.pow(Lbarp - 50, 2)) /
      Math.sqrt(20 + Math.pow(Lbarp - 50, 2));
  const Sc = 1 + 0.045 * Cbarp;
  const Sh = 1 + 0.015 * Cbarp * T;
  const Rt = -Math.sin(degToRad(2 * dTheta)) * Rc;

  const dE = Math.sqrt(
    Math.pow(dLp / Sl, 2) +
      Math.pow(dCp / Sc, 2) +
      Math.pow(dHp / Sh, 2) +
      Rt * (dCp / Sc) * (dHp / Sh),
  );
  return dE;
}

function hueAngleDeg(b, ap) {
  if (b === 0 && ap === 0) return 0;
  const angle = (Math.atan2(b, ap) * 180) / Math.PI;
  return angle >= 0 ? angle : angle + 360;
}

function degToRad(d) {
  return (d * Math.PI) / 180;
}
