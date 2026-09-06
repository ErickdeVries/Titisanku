import { ImageManipulator, SaveFormat } from "expo-image-manipulator";

/**
 * Resize + compress an image before upload so photos are lighter (hemat kuota)
 * and load faster. Falls back to the original uri if manipulation fails.
 */
export async function compressImage(uri: string, maxDim = 1080, compress = 0.6): Promise<string> {
  try {
    const context = ImageManipulator.manipulate(uri);
    context.resize({ width: maxDim });
    const rendered = await context.renderAsync();
    const result = await rendered.saveAsync({ compress, format: SaveFormat.JPEG });
    return result.uri;
  } catch {
    return uri;
  }
}
