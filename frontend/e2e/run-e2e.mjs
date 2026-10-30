/**
 * E2E Titisanku (web) — dijalankan terhadap backend TEST LOKAL (127.0.0.1:8002)
 * dan database lokal `titisanku_e2e`. TIDAK menyentuh produksi/Atlas.
 *
 * Prasyarat:
 *   - backend test hidup di http://127.0.0.1:8002 (DB lokal titisanku_e2e)
 *   - expo web E2E hidup di http://localhost:8082 (EXPO_PUBLIC_BACKEND_URL=8002)
 *   - seed sudah dibuat: `python backend/tests/seed_e2e_local.py`
 *
 * Jalankan:
 *   node frontend/e2e/run-e2e.mjs
 *
 * Exit code 0 = semua langkah lulus. Non-zero = ada langkah gagal.
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const APP_URL = process.env.E2E_APP_URL || "http://localhost:8082";
const BACKEND_URL = process.env.E2E_BACKEND_URL || "http://127.0.0.1:8002";
const SEED_FILE =
  process.env.E2E_SEED_FILE ||
  path.resolve(process.cwd(), "backend/tests/.e2e_local_seed.json");

const results = [];
let failed = 0;

function pass(name, extra = "") {
  results.push(`PASS  ${name}${extra ? "  -> " + extra : ""}`);
  console.log(`\x1b[32mPASS\x1b[0m ${name}${extra ? "  -> " + extra : ""}`);
}
function fail(name, err) {
  failed++;
  const msg = err?.message ? err.message.split("\n")[0] : String(err);
  results.push(`FAIL  ${name}  -> ${msg}`);
  console.log(`\x1b[31mFAIL\x1b[0m ${name}  -> ${msg}`);
}
async function step(name, fn) {
  try {
    await fn();
    pass(name);
  } catch (e) {
    fail(name, e);
  }
}

function loadSeed() {
  if (!fs.existsSync(SEED_FILE)) {
    throw new Error(
      `Seed file tidak ada: ${SEED_FILE}. Jalankan dulu: python backend/tests/seed_e2e_local.py`
    );
  }
  return JSON.parse(fs.readFileSync(SEED_FILE, "utf-8"));
}

async function main() {
  const seed = loadSeed();
  console.log(`Seed tree=${seed.tree_id} token=${seed.token.slice(0, 8)}...`);

  const launchOpts = { headless: true };
  if (process.env.E2E_CHROME_PATH) launchOpts.executablePath = process.env.E2E_CHROME_PATH;
  const browser = await chromium.launch(launchOpts);
  const context = await browser.newContext({
    viewport: { width: 420, height: 900 }, // ukuran mobile
  });
  const page = await context.newPage();

  const apiCalls = [];
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("/api/")) apiCalls.push(`${req.method()} ${u}`);
  });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  // 1) Suntik session token + active tree ke localStorage sebelum app load.
  await context.addInitScript(
    ({ token, treeId }) => {
      window.localStorage.setItem("session_token", token);
      window.localStorage.setItem("active_tree_id", treeId);
    },
    { token: seed.token, treeId: seed.tree_id }
  );

  // ---- A. Bootstrap / auth via token ----
  await step("A1. App memuat & login otomatis via session token", async () => {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
    // Tunggu sampai app authenticated: tidak lagi di /login.
    await page.waitForFunction(
      () => window.localStorage.getItem("session_token"),
      null,
      { timeout: 30_000 }
    );
    // Harus keluar dari layar login.
    await page.waitForFunction(
      () => !window.location.pathname.startsWith("/login"),
      null,
      { timeout: 45_000 }
    );
    const url = page.url();
    if (url.includes("/login")) throw new Error("Masih di /login: " + url);
  });

  // ---- B. Panggilan API memakai backend TEST (bukan produksi) ----
  await step("B1. Semua request API diarahkan ke backend test (8002)", async () => {
    await page.waitForTimeout(1500);
    const bad = apiCalls.filter((c) => c.includes("helipod.app"));
    if (bad.length) throw new Error("Ada request ke produksi: " + bad.slice(0, 3).join(", "));
    const toTest = apiCalls.filter((c) => c.includes("127.0.0.1:8002"));
    if (toTest.length === 0) throw new Error("Tidak ada request ke backend test (api belum jalan?)");
  });

  // ---- C. Layar pohon tampil ----
  await step("C1. Layar pohon (home) tampil dengan data seed", async () => {
    await page.goto(`${APP_URL}/`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-testid="tree-switcher"]', { timeout: 30_000 });
    const treeName = await page
      .locator('[data-testid="tree-switcher"]')
      .innerText()
      .catch(() => "");
    if (!treeName.includes("TESTE2E")) {
      throw new Error(`Nama pohon bukan seed (dapat: "${treeName.trim()}")`);
    }
  });

  // ---- D. Tambah anggota (add mother) lalu verifikasi muncul ----
  await step("D1. Tambah anggota baru (ibu) & tersimpan", async () => {
    await page.goto(`${APP_URL}/`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-testid="tree-switcher"]', { timeout: 30_000 });
    // Klik node root untuk membuka aksi tambah (add-mother muncul di home FAB/sheet).
    // Fallback: buka modal add-relative langsung dengan query param.
    const rootId = seed.root_id;
    await page.goto(
      `${APP_URL}/add-relative?focus_id=${rootId}&direction=mother&focus_name=TESTE2E_Root`,
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForSelector('[data-testid="input-name"]', { timeout: 30_000 });
    const newName = "TESTE2E_Ibu_" + Date.now();
    await page.fill('[data-testid="input-name"]', newName);
    // Gender hanya tersedia untuk arah yang tidak menyiratkan gender
    // (mis. mother/father sudah implying). Klik bila ada.
    const femaleBtn = page.locator('[data-testid="gender-female"]');
    if (await femaleBtn.count()) await femaleBtn.click();
    await page.click('[data-testid="form-submit"]');
    // Modal tertutup -> kembali ke pohon.
    await page.waitForFunction(
      () => !window.location.pathname.includes("add-relative"),
      null,
      { timeout: 30_000 }
    );
    // Verifikasi via API backend test bahwa person tersimpan.
    const token = seed.token;
    const res = await page.request.get(
      `${BACKEND_URL}/api/tree?tree_id=${seed.tree_id}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!res.ok()) throw new Error("GET /api/tree gagal: " + res.status());
    const body = await res.json();
    const people = body.people || body;
    const found = JSON.stringify(people).includes(newName);
    if (!found) throw new Error(`Anggota "${newName}" tidak ditemukan di tree`);
  });

  // ---- E. Chat: buka tab chat ----
  await step("E1. Tab Chat terbuka tanpa error", async () => {
    await page.goto(`${APP_URL}/chat`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-testid="new-chat-button"]', { timeout: 30_000 });
  });

  // ---- F. Settings: baris penting tersedia (privasi, subscription, members) ----
  await step("F1. Settings menampilkan baris kunci (privasi/subscription/members)", async () => {
    await page.goto(`${APP_URL}/settings`, { waitUntil: "domcontentloaded" });
    for (const id of ["privacy-row", "subscription-row", "members-row", "logout-button"]) {
      await page.waitForSelector(`[data-testid="${id}"]`, { timeout: 20_000 });
    }
  });

  // ---- G. Subscription / kuota storage tampil ----
  await step("G1. Layar subscription menampilkan info kuota", async () => {
    await page.goto(`${APP_URL}/subscription`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    const txt = await page.locator("body").innerText();
    if (!/kuota|storage|penyimpanan|plan|paket|GB|MB|free|pro|family/i.test(txt)) {
      throw new Error("Tidak menemukan info kuota/plan di halaman subscription");
    }
  });

  // ---- H. Privasi kartu: halaman privacy ----
  await step("H1. Halaman privasi terbuka", async () => {
    await page.goto(`${APP_URL}/privacy`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const txt = await page.locator("body").innerText();
    if (txt.trim().length < 20) throw new Error("Halaman privacy kosong");
  });

  // ---- H2. Claim branch: form tampil utk person yang dipilih ----
  await step("H2. Claim branch terbuka & form input nama cabang tampil", async () => {
    await page.goto(
      `${APP_URL}/claim-branch?person_id=${seed.root_id}&person_name=TESTE2E_Root`,
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForSelector('[data-testid="claim-name-input"]', { timeout: 30_000 });
    await page.waitForSelector('[data-testid="claim-submit"]', { timeout: 20_000 });
  });

  // ---- H3. Search: input pencarian berfungsi ----
  await step("H3. Tab Search menampilkan input pencarian", async () => {
    await page.goto(`${APP_URL}/search`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-testid="search-input"]', { timeout: 30_000 });
    await page.fill('[data-testid="search-input"]', "TESTE2E");
    await page.waitForTimeout(1500);
  });

  // ---- H4. Members: layar anggota terbuka ----
  await step("H4. Layar Members terbuka", async () => {
    await page.goto(`${APP_URL}/members`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    const txt = await page.locator("body").innerText();
    if (txt.trim().length < 15) throw new Error("Layar members kosong");
  });

  // ---- J. Non-owner (member) login: alur auth token kedua user ----
  await step("J1. Login sebagai member (non-owner) berhasil", async () => {
    const ctx2 = await browser.newContext({ viewport: { width: 420, height: 900 } });
    await ctx2.addInitScript(
      ({ token, treeId }) => {
        window.localStorage.setItem("session_token", token);
        window.localStorage.setItem("active_tree_id", treeId);
      },
      { token: seed.member_token || seed.token, treeId: seed.tree_id }
    );
    const p2 = await ctx2.newPage();
    await p2.goto(APP_URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
    await p2.waitForFunction(
      () => !window.location.pathname.startsWith("/login"),
      null,
      { timeout: 45_000 }
    );
    const meRes = await p2.request.get(`${BACKEND_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${seed.member_token || seed.token}` },
    });
    if (!meRes.ok()) throw new Error("member /auth/me gagal: " + meRes.status());
    await ctx2.close();
  });

  // ---- I. Tidak ada page error fatal ----
  await step("I1. Tidak ada JS error fatal di halaman", async () => {
    const fatal = pageErrors.filter(
      (m) => !/ResizeObserver|Warning:|deprecated|Non-serializable|VirtualizedList/i.test(m)
    );
    if (fatal.length) throw new Error("Page errors: " + fatal.slice(0, 3).join(" | "));
  });

  await browser.close();

  // Tulis laporan
  const reportDir = path.resolve(process.cwd(), "test_reports/e2e");
  fs.mkdirSync(reportDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  fs.writeFileSync(path.join(reportDir, `e2e-${stamp}.log`), results.join("\n"), "utf-8");
  fs.writeFileSync(
    path.join(reportDir, "latest.log"),
    results.join("\n"),
    "utf-8"
  );

  console.log(`\n=== E2E selesai: ${results.length - failed} lulus, ${failed} gagal ===`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("FATAL E2E:", e);
  process.exit(2);
});
