/**
 * Getting a photograph small enough to send, without making it unreadable.
 *
 * A phone camera produces a 12-megapixel JPEG of about 4 MB. Almost none of that
 * helps: the model reads a nutrition panel from a fraction of the resolution,
 * and the rest is upload time on a phone connection and vision tokens on the
 * bill.
 *
 * But it cannot go too far the other way either. The interesting part of the
 * photo is six numbers in six-point type, often the smallest print on the pack.
 * Resize too hard and the model starts guessing, which is the one failure this
 * feature must not have.
 *
 * 1400px on the long edge is the compromise: a label filling a third of the
 * frame still lands around 60px of text height, which reads cleanly, and the
 * file comes out near 300 KB.
 */

/** Long edge in pixels. See above - this number is a legibility floor. */
const MAX_EDGE = 1400

/** JPEG quality. Below about 0.8, compression artefacts start eating thin digits. */
const QUALITY = 0.85

export interface PreparedImage {
  blob: Blob
  /** An object URL for the preview. The caller revokes it. */
  previewUrl: string
  width: number
  height: number
  bytes: number
}

/**
 * Decode, downscale and re-encode a camera file.
 *
 * Re-encoded as JPEG whatever came in, which also strips the EXIF the camera
 * attached - and phone EXIF carries GPS coordinates. Sending someone's kitchen
 * location to a third party along with a picture of their cereal is not a trade
 * anybody agreed to, and nothing here needs the metadata.
 */
export async function prepareImage(image: Blob): Promise<PreparedImage> {
  const bitmap = await createImageBitmap(image)

  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
  const width = Math.round(bitmap.width * scale)
  const height = Math.round(bitmap.height * scale)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) throw new Error('This browser cannot process the image.')
  // White rather than transparent: a PNG with an alpha channel flattens to black
  // otherwise, and a black nutrition panel is unreadable.
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, width, height)
  context.drawImage(bitmap, 0, 0, width, height)
  bitmap.close()

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', QUALITY),
  )
  if (!blob) throw new Error('Could not read that photo.')

  return {
    blob,
    previewUrl: URL.createObjectURL(blob),
    width,
    height,
    bytes: blob.size,
  }
}

/* --- deciding when a frame is worth sending -------------------------------- */

/**
 * ## Why the first version never fired
 *
 * It scored a frame as `horizontalRules * 0.5 + verticalRules * 0.25 +
 * denseText * 0.25` and captured above 0.57. The rule terms counted rows where
 * a quarter of the pixels changed sharply against the row above - which finds
 * the black bars of a US panel, but only while they are exactly parallel to the
 * sensor.
 *
 * Two degrees of tilt smears a bar across several rows and the term collapses
 * to zero. With it gone the other two terms cap at 0.5, so the threshold was
 * **arithmetically unreachable** - not unlikely, unreachable. Measured against a
 * rendered panel: 0.651 dead flat, 0.277 at two degrees, 0.027 at five. Nobody
 * holds a phone to two degrees, so it never fired at all, which is what was
 * reported.
 *
 * ## What this looks for instead
 *
 * Three signals, none of which assume the pack is square to the camera:
 *
 * | Signal | Why it is in here |
 * |---|---|
 * | **Ink** | A panel is dark print on a light background, covering a predictable slice of the frame. A wall covers none; a dim photo covers everything. |
 * | **Focus** | Sharp edges mean the lens has settled. Firing on a blurred frame spends a scan on an image the model cannot read. |
 * | **Banding** | Rows of text, looked for at several shear angles rather than one, so a tilted pack still reads as a table. |
 *
 * It is still deliberately a *worth-sending* signal rather than a classifier. It
 * does not identify food and cannot read a label; the server and the model
 * remain the things that decide whether a photograph is really a panel.
 */
export interface PanelReading {
  /** 0-1. The capture loop fires above `CAPTURE_CONFIDENCE`. */
  confidence: number
  /** Fraction of the crop that is ink. */
  ink: number
  /** 0-1 sharpness, measured against the frame's own contrast. */
  focus: number
  /** 0-1 strength of the best row-banding found across shear angles. */
  banding: number
  /** 0-1 gap between the light and dark populations. */
  separation: number
}

/** Fire above this, for `STABLE_FRAMES` frames running. */
export const CAPTURE_CONFIDENCE = 0.55

/** Consecutive qualifying frames before the shutter goes. About a second. */
export const STABLE_FRAMES = 3

/** Shear angles searched for rows of text, in degrees. Hand tilt lives in here. */
const SHEAR_DEGREES = [-10, -6, -3, 0, 3, 6, 10]

/** 0 outside `[hardLow, hardHigh]`, 1 inside `[softLow, softHigh]`, ramped between. */
function taper(value: number, hardLow: number, softLow: number,
               softHigh: number, hardHigh: number): number {
  if (value <= hardLow || value >= hardHigh) return 0
  if (value < softLow) return (value - hardLow) / (softLow - hardLow)
  if (value > softHigh) return (hardHigh - value) / (hardHigh - softHigh)
  return 1
}

/** Sharp enough to read. Below the floor nothing else about the frame matters. */
function focusGate(focus: number): number {
  return Math.max(0, Math.min(1, (focus - 0.15) / 0.2))
}

/** Otsu's method: the luminance that best splits a frame into ink and paper. */
function inkThreshold(luminance: Uint8Array): number {
  const histogram = new Uint32Array(256)
  for (let i = 0; i < luminance.length; i += 1) histogram[luminance[i]] += 1

  let sum = 0
  for (let v = 0; v < 256; v += 1) sum += v * histogram[v]

  let sumBelow = 0
  let countBelow = 0
  let best = 0
  let bestVariance = -1
  for (let v = 0; v < 256; v += 1) {
    countBelow += histogram[v]
    if (countBelow === 0) continue
    const countAbove = luminance.length - countBelow
    if (countAbove === 0) break
    sumBelow += v * histogram[v]
    const meanBelow = sumBelow / countBelow
    const meanAbove = (sum - sumBelow) / countAbove
    const variance = countBelow * countAbove * (meanBelow - meanAbove) ** 2
    if (variance > bestVariance) {
      bestVariance = variance
      best = v
    }
  }
  return best
}

/**
 * How strongly the ink falls into rows, searched across shear angles.
 *
 * Counting ink per scanline finds lines of text only while they are level.
 * Binning by `y - x * tan(angle)` instead, and keeping the best answer, finds
 * them on a pack held by a person - which is the only way anybody holds a pack.
 */
function rowBanding(ink: Uint8Array, width: number, height: number): number {
  let best = 0

  for (const degrees of SHEAR_DEGREES) {
    const slope = Math.tan((degrees * Math.PI) / 180)
    const pad = Math.ceil(Math.abs(slope) * width) + 1
    const profile = new Float32Array(height + pad * 2)

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (!ink[y * width + x]) continue
        profile[Math.round(y - (x - width / 2) * slope) + pad] += 1
      }
    }

    // Only the band that holds the text. The padding is empty by construction
    // and would drag the mean towards zero.
    let first = -1
    let last = -1
    for (let i = 0; i < profile.length; i += 1) {
      if (profile[i] > 0) {
        if (first < 0) first = i
        last = i
      }
    }
    if (first < 0 || last - first < 8) continue

    let total = 0
    for (let i = first; i <= last; i += 1) total += profile[i]
    const mean = total / (last - first + 1)
    if (mean <= 0) continue

    // Lines of type cross their own mean twice each, so counting crossings
    // measures "ruled text" without caring how tall the type is.
    let crossings = 0
    let above = profile[first] > mean
    for (let i = first + 1; i <= last; i += 1) {
      const nowAbove = profile[i] > mean
      if (nowAbove !== above) {
        crossings += 1
        above = nowAbove
      }
    }

    best = Math.max(best, Math.min(crossings / 18, 1))
  }

  return best
}

/**
 * Score one frame. `PanelReading` above says what the three signals are.
 *
 * Pure: pixels in, numbers out, which is what lets `imageCapture.test.ts` hold
 * it to a table of cases rather than to a demonstration.
 */
export function readPanel(image: ImageData): PanelReading {
  const { data, width, height } = image
  const empty: PanelReading = { confidence: 0, ink: 0, focus: 0, banding: 0, separation: 0 }
  if (width < 32 || height < 32) return empty

  const luminance = new Uint8Array(width * height)
  for (let i = 0; i < luminance.length; i += 1) {
    const p = i * 4
    luminance[i] = Math.round(
      data[p] * 0.2126 + data[p + 1] * 0.7152 + data[p + 2] * 0.0722,
    )
  }

  // Otsu rather than a fixed cutoff, because a fixed one is what made a dimly
  // lit kitchen score 0.006. A panel under a weak bulb is still a panel.
  const threshold = inkThreshold(luminance)
  const mask = new Uint8Array(luminance.length)
  let inkCount = 0
  let inkSum = 0
  let paperSum = 0
  for (let i = 0; i < luminance.length; i += 1) {
    // `<=`, not `<`: Otsu returns the last level of the dark class, so the
    // strict form drops every pixel at exactly that level - which on flat art
    // is all of the ink there is.
    if (luminance[i] <= threshold) {
      mask[i] = 1
      inkCount += 1
      inkSum += luminance[i]
    } else {
      paperSum += luminance[i]
    }
  }
  const paperCount = luminance.length - inkCount
  if (inkCount === 0 || paperCount === 0) return empty

  const separation = ((paperSum / paperCount) - (inkSum / inkCount)) / 255
  const ink = inkCount / luminance.length

  // A flat surface splits into two halves that barely differ. Printing does not.
  if (separation < 0.14) return { ...empty, ink, separation }

  // Print covers a slice of the frame, neither a sliver nor most of it. Too
  // little is a label too far away to read; too much is a dark frame, or a
  // small panel against a background darker than its paper.
  const inkGate = taper(ink, 0.02, 0.05, 0.34, 0.6)

  // Sharpness, as the share of edges that are steep.
  //
  // Two earlier attempts got this wrong in opposite directions. Averaging the
  // gradient over the whole frame measures how much print there is, not how
  // sharp it is - and blurring actually *raises* it, by smearing each edge over
  // more pixels. Averaging only above a floor then flatters a blurred edge,
  // because the floor throws away the shallow half of it and keeps the steep
  // middle.
  //
  // A ratio avoids both. A settled lens puts the whole ink-to-paper step into
  // one pixel, so nearly every edge it finds is a steep one. A soft lens spreads
  // that step over several pixels, so almost none of them are.
  const contrast = separation * 255
  let steep = 0
  let anyEdge = 0
  for (let y = 1; y < height; y += 1) {
    for (let x = 1; x < width; x += 1) {
      const i = y * width + x
      const step = Math.max(
        Math.abs(luminance[i] - luminance[i - 1]),
        Math.abs(luminance[i] - luminance[i - width]),
      )
      if (step > contrast * 0.1) anyEdge += 1
      if (step > contrast * 0.45) steep += 1
    }
  }
  const focus = anyEdge === 0 ? 0 : steep / anyEdge

  const banding = rowBanding(mask, width, height)

  // Rows of text are the signal. Ink and focus are preconditions, so they
  // multiply rather than vote: a beautifully banded frame that is out of focus
  // is not worth a scan, and no amount of banding should outvote that. Scoring
  // all three as a weighted sum is what let a blurred frame pass on banding
  // alone.
  return {
    confidence: (0.25 + 0.75 * banding) * inkGate * focusGate(focus),
    ink,
    focus,
    banding,
    separation,
  }
}

/** The number the capture loop compares against `CAPTURE_CONFIDENCE`. */
export function nutritionTableConfidence(image: ImageData): number {
  return readPanel(image).confidence
}

/**
 * How much two consecutive detector frames differ, 0-1.
 *
 * The old loop counted qualifying frames and called that steady, which it is
 * not: three good frames taken while panning along a shelf are three good
 * frames of three different things. Comparing them makes "hold steady" mean
 * what it says, and makes the shutter wait for the hand to stop.
 */
export function frameDifference(a: ImageData, b: ImageData): number {
  if (a.width !== b.width || a.height !== b.height) return 1
  let total = 0
  const pixels = a.width * a.height
  for (let i = 0; i < pixels; i += 1) {
    const p = i * 4
    total += Math.abs(
      (a.data[p] + a.data[p + 1] + a.data[p + 2])
      - (b.data[p] + b.data[p + 1] + b.data[p + 2]),
    ) / 3
  }
  return total / (pixels * 255)
}

/** Frames differing by more than this are still moving. */
export const STEADY_DIFFERENCE = 0.055

/**
 * The part of the video the person is actually aiming with.
 *
 * The preview is `object-cover` inside a 4:3 box, so a 16:9 stream loses its
 * left and right edges before anybody sees them, and the guide rectangle insets
 * further. Scoring the raw frame scores a wider view than the one being aimed:
 * the detector judging pixels the person cannot see, and ignoring the framing
 * they were asked to get right.
 */
export function reticleSource(
  videoWidth: number, videoHeight: number, boxAspect = 4 / 3, inset = 0.12,
): { sx: number; sy: number; sw: number; sh: number } {
  let sw = videoWidth
  let sh = videoHeight
  if (videoWidth / videoHeight > boxAspect) sw = videoHeight * boxAspect
  else sh = videoWidth / boxAspect

  const insetX = sw * inset
  const insetY = sh * inset
  return {
    sx: (videoWidth - sw) / 2 + insetX,
    sy: (videoHeight - sh) / 2 + insetY,
    sw: sw - insetX * 2,
    sh: sh - insetY * 2,
  }
}
