// One QueryClient for the whole app; the provider in app/_layout.tsx uses
// this instance. Import it for cache calls outside components, for example
// queryClient.invalidateQueries or setQueryData in websocket or push
// handlers; inside components useQueryClient() returns this same instance.
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data keluarga jarang berubah dalam hitungan detik: 30 detik cukup
      // untuk mencegah refetch berulang saat berpindah tab / buka-tutup layar.
      staleTime: 30_000,
      // Simpan di memori sehari supaya layar yang ditutup-buka tidak perlu
      // memuat ulang (dipakai bersama cache AsyncStorage di offline-cache.ts).
      gcTime: 24 * 60 * 60 * 1000,
      retry: 1,
      // Di HP, "window focus" berubah setiap app kembali ke depan; refetch
      // otomatis di situ memakan kuota tanpa diminta pengguna.
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
});
