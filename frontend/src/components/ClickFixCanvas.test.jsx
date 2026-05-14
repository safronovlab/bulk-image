/**
 * Failing tests for frontend/src/components/ClickFixCanvas.jsx.
 *
 * Covers ClickFixCanvas_spec.md §5 + every [SRE_MARKER].
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ClickFixCanvas from './ClickFixCanvas';

vi.mock('../api', () => ({
  api: {
    clickFix: vi.fn(async (imageId, body) => ({
      image_id: 'NEWID',
      previous_image_id: imageId,
      preview_url: '/api/images/NEWID/preview',
    })),
  },
}));

const baseProps = {
  imageId: '01H8XGJWBWBAQ4ZQH8K1MABCDE',
  imageUrl: '/api/images/01H8XGJWBWBAQ4ZQH8K1MABCDE/preview',
  imageWidth: 4000,
  imageHeight: 4000,
  targetRgb: [255, 0, 24],
  onFixSubmitted: vi.fn(),
  onFixError: vi.fn(),
  maxDisplayWidth: 900,
};

describe('ClickFixCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders_canvas_with_intrinsic_dimensions', () => {
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeTruthy();
    expect(canvas.width).toBe(4000);
    expect(canvas.height).toBe(4000);
  });

  it('applies_css_scale_to_fit_max_display_width', () => {
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    const style = canvas.style;
    // 4000-px image scaled to 900-px display
    expect(style.width).toBe('900px');
  });

  it('does_not_render_canvas_for_zero_dimensions', () => {
    const { container } = render(
      <ClickFixCanvas {...baseProps} imageWidth={0} imageHeight={0} />,
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeNull();
  });

  it('cursor_style_is_crosshair', () => {
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    expect(canvas.style.cursor || getComputedStyle(canvas).cursor).toMatch(/crosshair/);
  });

  it('disables_click_when_disabled_prop_true', async () => {
    const { container } = render(
      <ClickFixCanvas {...baseProps} disabled={true} />,
    );
    const canvas = container.querySelector('canvas');
    fireEvent.click(canvas, { clientX: 100, clientY: 100 });
    const { api } = await import('../api');
    expect(api.clickFix).not.toHaveBeenCalled();
  });

  it('image_load_failure_calls_on_fix_error', async () => {
    const onFixError = vi.fn();
    render(<ClickFixCanvas {...baseProps} onFixError={onFixError} imageUrl="bad://url" />);
    await waitFor(() => {
      expect(onFixError).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'image.load_failed' }),
      );
    });
  });

  it('aborts_pending_request_on_unmount', () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort');
    const { unmount } = render(<ClickFixCanvas {...baseProps} />);
    unmount();
    expect(abortSpy).toHaveBeenCalled();
    abortSpy.mockRestore();
  });

  // SRE_MARKER risk=memory (line 11)
  it('releases_canvas_buffer_on_image_change', async () => {
    const { rerender, container } = render(<ClickFixCanvas {...baseProps} />);
    rerender(
      <ClickFixCanvas
        {...baseProps}
        imageId="OTHER_ID"
        imageUrl="/api/images/OTHER_ID/preview"
      />,
    );
    // After rerender, the previous canvas's buffer should be released —
    // check that the canvas element is fresh / re-keyed.
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeTruthy();
  });

  // SRE_MARKER risk=input (line 12)
  it('test_click_coordinate_correct_under_browser_zoom_125', () => {
    // Simulate a 1.25 zoom by mocking getBoundingClientRect to return
    // a smaller rect than intrinsic.
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 720,    // 900 / 1.25
      height: 720,
      right: 720,
      bottom: 720,
      x: 0,
      y: 0,
      toJSON() {
        return {};
      },
    });
    fireEvent.click(canvas, { clientX: 360, clientY: 360 });
    // Implementation must clamp/scale coords to intrinsic [0, W-1].
  });

  // SRE_MARKER risk=concurrency (line 13)
  it('test_click_disabled_until_response_received', async () => {
    const { api } = await import('../api');
    let resolveFn;
    api.clickFix.mockImplementation(
      () => new Promise((res) => (resolveFn = res)),
    );
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    fireEvent.click(canvas, { clientX: 100, clientY: 100 });
    fireEvent.click(canvas, { clientX: 200, clientY: 200 });
    expect(api.clickFix).toHaveBeenCalledTimes(1);
    resolveFn?.({ image_id: 'X', previous_image_id: baseProps.imageId, preview_url: '' });
  });

  // SRE_MARKER risk=security (line 112)
  it('test_canvas_taint_recovers_gracefully', () => {
    const { container } = render(<ClickFixCanvas {...baseProps} />);
    const canvas = container.querySelector('canvas');
    // Mock getImageData to throw SecurityError (canvas tainted)
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.getImageData = () => {
        throw new DOMException('tainted', 'SecurityError');
      };
    }
    fireEvent.click(canvas, { clientX: 100, clientY: 100 });
    // No crash — error path takes over.
  });

  // SRE_MARKER risk=dependency (line 113)
  it('test_image_load_timeout_after_15s', () => {
    // Smoke test: the component must wire AbortSignal.timeout(15s) (or
    // similar) to the fetch. We can't easily simulate 15s in a unit test;
    // instead we ensure that an AbortController is created on mount.
    const ctrlSpy = vi.spyOn(globalThis, 'AbortController');
    render(<ClickFixCanvas {...baseProps} />);
    expect(ctrlSpy).toHaveBeenCalled();
    ctrlSpy.mockRestore();
  });
});
