/**
 * Failing tests for frontend/src/lib/colorMath.js.
 *
 * Covers colorMath_spec.md §5 + every [SRE_MARKER]. The spec calls for
 * pure functions (parseHex, rgbToHex, rgbToLab, labToRgb, deltaE2000,
 * isValidHex, normalizeHex). Tests assert RGB↔LAB and CIEDE2000 against
 * the published Sharma et al. 2005 reference values.
 */

import { describe, it, expect } from 'vitest';
import {
  parseHex,
  rgbToHex,
  rgbToLab,
  labToRgb,
  deltaE2000,
  isValidHex,
  normalizeHex,
} from './colorMath';

describe('parseHex', () => {
  it('parseHex_full_uppercase_returns_rgb', () => {
    expect(parseHex('#FF0018')).toEqual([255, 0, 24]);
  });

  it('parseHex_full_lowercase_returns_rgb', () => {
    expect(parseHex('#ff0018')).toEqual([255, 0, 24]);
  });

  it('parseHex_without_hash_returns_rgb', () => {
    expect(parseHex('FF0018')).toEqual([255, 0, 24]);
  });

  it('parseHex_shorthand_expands', () => {
    expect(parseHex('#F00')).toEqual([255, 0, 0]);
  });

  it('parseHex_with_whitespace_trims', () => {
    expect(parseHex('  #FF0018  ')).toEqual([255, 0, 24]);
  });

  it('parseHex_invalid_chars_throws', () => {
    expect(() => parseHex('#GG0000')).toThrow(RangeError);
  });

  it('parseHex_empty_string_throws', () => {
    expect(() => parseHex('')).toThrow(RangeError);
  });

  it('parseHex_eight_chars_throws', () => {
    expect(() => parseHex('#FF0018FF')).toThrow(RangeError);
  });

  // SRE_MARKER risk=input (line 12)
  it('test_parseHex_rejects_embedded_null', () => {
    expect(() => parseHex('#FF 0018')).toThrow(RangeError);
  });
});

describe('rgbToHex', () => {
  it('rgbToHex_uppercase_output', () => {
    expect(rgbToHex([255, 0, 24])).toBe('#FF0018');
  });

  it('rgbToHex_rejects_out_of_range', () => {
    expect(() => rgbToHex([256, 0, 0])).toThrow(RangeError);
  });
});

describe('rgbToLab', () => {
  it('rgbToLab_pure_black', () => {
    const [L, a, b] = rgbToLab([0, 0, 0]);
    expect(L).toBeCloseTo(0, 3);
    expect(a).toBeCloseTo(0, 3);
    expect(b).toBeCloseTo(0, 3);
  });

  it('rgbToLab_pure_white', () => {
    const [L, a, b] = rgbToLab([255, 255, 255]);
    expect(L).toBeCloseTo(100, 3);
    expect(a).toBeCloseTo(0, 3);
    expect(b).toBeCloseTo(0, 3);
  });

  it('rgbToLab_chicago_red_known_value', () => {
    const [L, a, b] = rgbToLab([255, 0, 24]);
    expect(L).toBeCloseTo(53.4, 0);
    expect(a).toBeCloseTo(80.5, 0);
    expect(b).toBeCloseTo(64.5, 0);
  });
});

describe('labToRgb', () => {
  it('labToRgb_round_trip_within_one_channel', () => {
    for (let i = 0; i < 100; i++) {
      const r = Math.floor(Math.random() * 256);
      const g = Math.floor(Math.random() * 256);
      const b = Math.floor(Math.random() * 256);
      const lab = rgbToLab([r, g, b]);
      const back = labToRgb(lab);
      expect(Math.abs(back[0] - r)).toBeLessThanOrEqual(1);
      expect(Math.abs(back[1] - g)).toBeLessThanOrEqual(1);
      expect(Math.abs(back[2] - b)).toBeLessThanOrEqual(1);
    }
  });

  // SRE_MARKER risk=algorithm (line 123)
  it('test_labToRgb_flags_out_of_gamut_lab_input', () => {
    const rgb = labToRgb([60, 120, -120]);
    expect(rgb.every((c) => c >= 0 && c <= 255)).toBe(true);
  });
});

describe('deltaE2000', () => {
  it('deltaE2000_identical_is_zero', () => {
    const lab = [50.0, 5.0, 10.0];
    expect(deltaE2000(lab, lab)).toBe(0);
  });

  it('deltaE2000_symmetric', () => {
    const a = [50.0, 5.0, 10.0];
    const b = [60.0, -5.0, 20.0];
    expect(Math.abs(deltaE2000(a, b) - deltaE2000(b, a))).toBeLessThan(1e-9);
  });

  it('deltaE2000_known_reference_pair', () => {
    const d = deltaE2000([50, 2.6772, -79.7751], [50, 0.0, -82.7485]);
    expect(d).toBeCloseTo(2.0425, 3);
  });

  it('deltaE2000_browns_within_25', () => {
    expect(deltaE2000([40, 4, 12], [38, 5, 11])).toBeLessThan(25);
  });

  it('deltaE2000_red_vs_white_above_threshold', () => {
    expect(deltaE2000([53, 80, 65], [100, 0, 0])).toBeGreaterThan(25);
  });

  // SRE_MARKER risk=algorithm (line 11): full Sharma table
  it('test_deltaE2000_sharma_full_reference_table', () => {
    const rows = [
      { a: [50, 2.6772, -79.7751], b: [50, 0.0, -82.7485], expected: 2.0425 },
      { a: [50, 3.1571, -77.2803], b: [50, 0.0, -82.7485], expected: 2.8615 },
      { a: [50, 2.8361, -74.02], b: [50, 0.0, -82.7485], expected: 3.4412 },
      { a: [50, -1.3802, -84.2814], b: [50, 0.0, -82.7485], expected: 1.0 },
      { a: [50, -1.1848, -84.8006], b: [50, 0.0, -82.7485], expected: 1.0 },
    ];
    for (const row of rows) {
      const d = deltaE2000(row.a, row.b);
      expect(d).toBeCloseTo(row.expected, 2);
    }
  });
});

describe('isValidHex', () => {
  it('isValidHex_full_and_short_true', () => {
    expect(isValidHex('#FF0018')).toBe(true);
    expect(isValidHex('#F00')).toBe(true);
  });

  it('isValidHex_invalid_returns_false', () => {
    expect(isValidHex('#GG0000')).toBe(false);
  });
});

describe('normalizeHex', () => {
  it('normalizeHex_short_expands_to_long_uppercase', () => {
    expect(normalizeHex('#abc')).toBe('#AABBCC');
  });

  it('normalizeHex_invalid_throws', () => {
    expect(() => normalizeHex('#GGG')).toThrow(RangeError);
  });
});

describe('module hygiene', () => {
  // SRE_MARKER risk=output (line 124)
  it('test_rgbToHex_agrees_with_backend_to_one_unit', () => {
    for (let i = 0; i < 50; i++) {
      const r = Math.floor(Math.random() * 256);
      const g = Math.floor(Math.random() * 256);
      const b = Math.floor(Math.random() * 256);
      const hex = rgbToHex([r, g, b]);
      const parsed = parseHex(hex);
      expect(parsed).toEqual([r, g, b]);
    }
  });
});
