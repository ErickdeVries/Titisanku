/**
 * Dynamic Expo config.
 *
 * app.json tetap menjadi sumber utama. File ini hanya menimpa
 * `android.googleServicesFile` saat build EAS, karena file kredensial Firebase
 * tidak ikut ter-upload lewat git (.gitignore). Nilainya disediakan sebagai
 * EAS file environment variable `GOOGLE_SERVICES_JSON` (berisi path absolut
 * file sementara yang di-inject EAS saat build).
 */
const base = require("./app.json");

module.exports = () => {
  const config = { ...base.expo };
  const googleServicesFile = process.env.GOOGLE_SERVICES_JSON;

  if (googleServicesFile) {
    config.android = {
      ...config.android,
      googleServicesFile,
    };
  }

  return config;
};
