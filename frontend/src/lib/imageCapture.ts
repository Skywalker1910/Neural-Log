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

/**
 * A deliberately conservative signal for the black rules and dense text of a
 * nutrition table. It does not identify food or read a label locally; it only
 * decides when a steady frame is worth sending to the existing vision reader.
 *
 * Requiring several positive frames keeps a passing barcode, a hand, or a
 * camera shake from immediately spending a scan. The server still validates
 * the image and can refuse a frame that is not a nutrition panel.
 */
export function nutritionTableConfidence(image: ImageData): number {
  const { data, width, height } = image
  if (width < 40 || height < 40) return 0

  const luminance = new Uint8Array(width * height)
  let total = 0
  for (let index = 0; index < luminance.length; index += 1) {
    const pixel = index * 4
    const value = Math.round(
      data[pixel] * 0.2126 + data[pixel + 1] * 0.7152 + data[pixel + 2] * 0.0722,
    )
    luminance[index] = value
    total += value
  }

  // A black frame and a blown-out frame can both have edges; neither is useful.
  const average = total / luminance.length
  if (average < 55 || average > 242) return 0

  let textured = 0
  let horizontalRules = 0
  let verticalRules = 0
  const threshold = 58

  for (let y = 1; y < height; y += 1) {
    let contrast = 0
    for (let x = 0; x < width; x += 1) {
      if (Math.abs(luminance[y * width + x] - luminance[(y - 1) * width + x]) > threshold) {
        contrast += 1
      }
    }
    textured += contrast
    if (contrast > width * 0.27) horizontalRules += 1
  }

  for (let x = 1; x < width; x += 1) {
    let contrast = 0
    for (let y = 0; y < height; y += 1) {
      if (Math.abs(luminance[y * width + x] - luminance[y * width + x - 1]) > threshold) {
        contrast += 1
      }
    }
    textured += contrast
    if (contrast > height * 0.2) verticalRules += 1
  }

  const texture = textured / ((width * (height - 1) + height * (width - 1)) || 1)
  const horizontal = Math.min(horizontalRules / 5, 1)
  const vertical = Math.min(verticalRules / 4, 1)
  const denseText = Math.min(texture / 0.16, 1)
  return horizontal * 0.5 + vertical * 0.25 + denseText * 0.25
}
