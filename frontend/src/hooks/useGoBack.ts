import { useCallback } from "react";
import { useRouter } from "expo-router";
import type { Href } from "expo-router";

/**
 * Safe back navigation.
 *
 * `router.back()` throws / logs "The action 'GO_BACK' was not handled by any
 * navigator" whenever the screen was opened directly (deep link, browser
 * refresh, or the first entry of the history stack). In that case we fall back
 * to a known route instead of doing nothing.
 */
export function useGoBack(fallback: Href = "/") {
  const router = useRouter();

  return useCallback(() => {
    try {
      if (router.canGoBack?.()) {
        router.back();
        return;
      }
    } catch {
      // canGoBack is not available on every platform/build — fall through.
    }
    router.replace(fallback);
  }, [router, fallback]);
}
