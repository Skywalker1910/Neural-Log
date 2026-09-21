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
export async function prepareImage(file: File): Promise<PreparedImage> {
  const bitmap = await createImageBitmap(file)

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
