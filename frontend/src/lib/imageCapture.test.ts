/**
 * The auto-capture detector, against frames built on purpose.
 *
 * The first version of this function shipped with no tests and could not fire.
 * It scored the black rules of a nutrition panel by counting sharp changes
 * between adjacent scanlines, which works only while the pack is parallel to
 * the sensor: two degrees of tilt took it from 0.651 to 0.277, and because that
 * term carried half the weight against a 0.57 threshold, the remaining terms
 * could not reach the bar on their own. Not unlikely - unreachable.
 *
 * A browser could not have caught that, because the camera always looked fine.
 * Only numbers catch it, so these are numbers: synthetic panels rendered into
 * plain pixel buffers, with the tilt, focus and lighting dialled by hand.
 */
import { describe, expect, it } from 'vitest'

import {
  CAPTURE_CONFIDENCE,
  STEADY_DIFFERENCE,
  frameDifference,
  readPanel,
  reticleSource,
} from './imageCapture'

interface PanelOptions {
  width?: number
  height?: number
  /** Degrees of rotation, as a hand holds a packet. */
  tilt?: number
  /** Box-blur radius in pixels. 0 is a lens that has settled. */
  blur?: number
  /** Paper luminance. Low is a dim kitchen, not a different kind of label. */
  paper?: number
  /** Ink luminance. */
  ink?: number
  /** Lines of type. */
  rows?: number
  /** Stroke height in pixels. Fat strokes are how a frame becomes mostly ink. */
  thickness?: number
  /** Peak sensor noise, in luminance levels. A real camera is never clean. */
  noise?: number
}

/**
 * A nutrition panel as pixels: lines of type on paper, optionally tilted.
 *
 * Deliberately crude. The detector looks for rows of ink at some angle, in
 * focus, covering a plausible share of the frame - so a fixture only has to be
 * honest about those, and a fixture that drew realistic glyphs would be testing
 * the fixture.
 */
function panel(options: PanelOptions = {}): ImageData {
  const {
    width = 240, height = 180, tilt = 0, blur = 0,
    paper = 244, ink = 24, rows = 14, thickness, noise = 0,
  } = options

  const luminance = new Float32Array(width * height).fill(paper)
  const slope = Math.tan((tilt * Math.PI) / 180)
  const spacing = height / (rows + 2)

  for (let row = 1; row <= rows; row += 1) {
    const baseline = row * spacing
    // Words: runs of ink with gaps, so a line is not a solid bar.
    for (let x = 6; x < width - 6; x += 1) {
      if (Math.floor(x / 7) % 4 === 3) continue
      const y = Math.round(baseline + (x - width / 2) * slope)
      const stroke = thickness ?? Math.max(2, Math.round(spacing * 0.42))
      for (let t = 0; t < stroke; t += 1) {
        const yy = y + t
        if (yy >= 0 && yy < height) luminance[yy * width + x] = ink
      }
    }
  }

  if (blur > 0) {
    const source = Float32Array.from(luminance)
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let total = 0
        let count = 0
        for (let dy = -blur; dy <= blur; dy += 1) {
          for (let dx = -blur; dx <= blur; dx += 1) {
            const yy = y + dy
            const xx = x + dx
            if (yy < 0 || yy >= height || xx < 0 || xx >= width) continue
            total += source[yy * width + xx]
            count += 1
          }
        }
        luminance[y * width + x] = total / count
      }
    }
  }

  if (noise > 0) {
    // Deterministic: a test that fails one run in twenty is worse than no test.
    let seed = 12345
    for (let i = 0; i < luminance.length; i += 1) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff
      luminance[i] += ((seed / 0x7fffffff) * 2 - 1) * noise
    }
  }

  const data = new Uint8ClampedArray(width * height * 4)
  for (let i = 0; i < luminance.length; i += 1) {
    const value = Math.round(luminance[i])
    data[i * 4] = value
    data[i * 4 + 1] = value
    data[i * 4 + 2] = value
    data[i * 4 + 3] = 255
  }
  return { data, width, height, colorSpace: 'srgb' } as ImageData
}

function flat(value: number, width = 240, height = 180): ImageData {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let i = 0; i < width * height; i += 1) {
    data[i * 4] = value
    data[i * 4 + 1] = value
    data[i * 4 + 2] = value
    data[i * 4 + 3] = 255
  }
  return { data, width, height, colorSpace: 'srgb' } as ImageData
}

describe('what the detector fires on', () => {
  it('fires on a panel squarely in frame', () => {
    expect(readPanel(panel()).confidence).toBeGreaterThan(CAPTURE_CONFIDENCE)
  })

  // The regression. Every one of these tilts used to score zero on the term
  // that carried half the weight, which put the threshold out of reach.
  it.each([2, 5, 8, 12])('still fires at %i degrees of tilt', (tilt) => {
    const reading = readPanel(panel({ tilt }))
    expect(reading.banding).toBeGreaterThan(0.5)
    expect(reading.confidence).toBeGreaterThan(CAPTURE_CONFIDENCE)
  })

  it('fires in a dim kitchen, because a dim panel is still a panel', () => {
    // The first version gave up below an absolute brightness. This one measures
    // the gap between ink and paper, which survives the light being bad.
    expect(readPanel(panel({ paper: 132, ink: 28 })).confidence)
      .toBeGreaterThan(CAPTURE_CONFIDENCE)
  })

  it('fires through the noise a real sensor adds', () => {
    // The fixtures are otherwise perfectly clean renders, which is not what a
    // phone in a kitchen produces. Grain adds a lot of shallow steps, and the
    // sharpness test is a ratio of steep steps to all of them - so this is the
    // case where being too strict would mean never firing on real hardware.
    expect(readPanel(panel({ noise: 8 })).confidence).toBeGreaterThan(CAPTURE_CONFIDENCE)
    expect(readPanel(panel({ noise: 16 })).confidence).toBeGreaterThan(CAPTURE_CONFIDENCE)
  })

  it('fires on a label with no heavy rules at all', () => {
    // EU packaging prints a plain grid. The old detector wanted black bars.
    expect(readPanel(panel({ rows: 10 })).confidence).toBeGreaterThan(CAPTURE_CONFIDENCE)
  })
})

describe('what it waits for', () => {
  it('waits while the lens is still settling', () => {
    const sharp = readPanel(panel())
    const soft = readPanel(panel({ blur: 4 }))
    expect(soft.focus).toBeLessThan(sharp.focus)
    expect(soft.confidence).toBeLessThan(CAPTURE_CONFIDENCE)
  })

  it('does not fire on a blank surface', () => {
    expect(readPanel(flat(238)).confidence).toBe(0)
    expect(readPanel(flat(18)).confidence).toBe(0)
  })

  it('does not fire on a frame that is nearly all ink', () => {
    // A pocket, a shadow, a thumb over the lens. The bands may look convincing;
    // what says it is not a label is how much of the frame the dark covers.
    const reading = readPanel(panel({ rows: 14, thickness: 11 }))
    expect(reading.ink).toBeGreaterThan(0.6)
    expect(reading.confidence).toBeLessThan(CAPTURE_CONFIDENCE)
  })

  it('refuses a frame too small to judge', () => {
    expect(readPanel(panel({ width: 24, height: 24 })).confidence).toBe(0)
  })
})

describe('holding steady', () => {
  it('reports no difference between a frame and itself', () => {
    expect(frameDifference(panel(), panel())).toBe(0)
  })

  it('reports a moving camera as moving', () => {
    // Counting qualifying frames called this steady. It is three good frames of
    // three different things.
    expect(frameDifference(panel(), panel({ tilt: 9 })))
      .toBeGreaterThan(STEADY_DIFFERENCE)
  })

  it('treats a changed frame size as movement rather than crashing', () => {
    expect(frameDifference(panel(), panel({ width: 200 }))).toBe(1)
  })
})

describe('the crop the person is aiming with', () => {
  it('takes the middle of a 16:9 stream shown in a 4:3 box', () => {
    const { sx, sy, sw, sh } = reticleSource(1920, 1080)
    // 1440x1080 is the visible part; the reticle insets 12% of that.
    expect(sw).toBeCloseTo(1440 * 0.76, 1)
    expect(sh).toBeCloseTo(1080 * 0.76, 1)
    // Centred: equal margins either side.
    expect(sx + sw / 2).toBeCloseTo(960, 1)
    expect(sy + sh / 2).toBeCloseTo(540, 1)
  })

  it('crops the other way for a tall stream', () => {
    const { sh } = reticleSource(720, 1280)
    expect(sh).toBeCloseTo((720 / (4 / 3)) * 0.76, 1)
  })

  it('stays inside the frame', () => {
    for (const [w, h] of [[1920, 1080], [1280, 720], [720, 1280], [640, 480]]) {
      const { sx, sy, sw, sh } = reticleSource(w, h)
      expect(sx).toBeGreaterThanOrEqual(0)
      expect(sy).toBeGreaterThanOrEqual(0)
      expect(sx + sw).toBeLessThanOrEqual(w + 0.001)
      expect(sy + sh).toBeLessThanOrEqual(h + 0.001)
    }
  })
})
