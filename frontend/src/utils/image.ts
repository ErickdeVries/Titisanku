import { ImageManipulator, SaveFormat } from "expo-image-manipulator";

import { fileUrl } from "@/src/api";

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

/**
 * Kunci cache gambar yang stabil.
 *
 * `fileUrl()` menempelkan token login ke query string, sehingga URL berubah
 * setiap sesi baru dan cache disk expo-image tidak pernah terpakai ulang.
 * Nama objek di storage memakai uuid (isinya tidak pernah berubah), jadi
 * path tanpa token adalah kunci cache yang tepat.
 */
export function imageCacheKey(pathOrUrl?: string | null): string | undefined {
  if (!pathOrUrl) return undefined;
  if (pathOrUrl.startsWith("http")) return pathOrUrl.split("?")[0];
  return pathOrUrl.replace("/api/files/", "").split("?")[0];
}

export type ImageProps = {
  source?: { uri: string | undefined };
  cacheKey?: string;
  cachePolicy?: "memory-disk";
};

/**
 * Props siap-pakai untuk `<Image>` expo-image. Kalau `thumb` tersedia, versi
 * 320px yang dipakai supaya kartu & daftar tidak menarik foto ukuran penuh.
 */
export function imageProps(full?: string | null, thumb?: string | null): ImageProps {
  const path = thumb || full;
  const uri = fileUrl(path);
  if (!uri) return {};
  return { source: { uri }, cacheKey: imageCacheKey(path), cachePolicy: "memory-disk" };
}

/** `imageProps` untuk objek bertipe Person (`photo_url` + `photo_thumb`). */
export function photoProps(person?: { photo_url?: string | null; photo_thumb?: string | null } | null): ImageProps {
  return imageProps(person?.photo_url, person?.photo_thumb);
}
