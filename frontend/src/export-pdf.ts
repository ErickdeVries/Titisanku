import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";
import { Person, Relation, fileUrl } from "@/src/api";
import { buildLayout, NODE_R } from "@/src/tree-layout";

const COLORS = {
  admin: "#F59E0B",
  male: "#3B82F6",
  female: "#EC4899",
  other: "#64748B",
  adopted: "#94A3B8",
  divorce: "#EF4444",
  relation: "#CBD5E1",
};

function personColor(p: Person) {
  if (p.is_root) return COLORS.admin;
  if (p.gender === "female") return COLORS.female;
  if (p.gender === "male") return COLORS.male;
  return COLORS.other;
}

function initials(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

function esc(s: any) {
  return String(s ?? "-").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Build the tree drawing as an <svg> tag string for the given generation range.
function buildTreeSvg(
  people: Person[],
  relations: Relation[],
  rootId: string | null,
  genUp: number,
  genDown: number,
) {
  const full = buildLayout(people, relations, rootId);
  const inRange = (g: number) => g >= -genUp && g <= genDown;
  const nodes = full.nodes.filter((n) => inRange(n.gen));
  if (nodes.length === 0) return { tag: "", nodes };
  const minX = Math.min(...nodes.map((n) => n.x)) - 60;
  const maxX = Math.max(...nodes.map((n) => n.x)) + 60;
  const minY = Math.min(...nodes.map((n) => n.y)) - 60;
  const maxY = Math.max(...nodes.map((n) => n.y)) + 60;
  const w = Math.max(maxX - minX, 200);
  const h = Math.max(maxY - minY, 200);
  const svgEdges = full.edges
    .map((e) => {
      const inV = e.y1 >= minY && e.y2 <= maxY;
      if (!inV) return "";
      const stroke = e.kind === "adopted" ? COLORS.adopted : e.kind === "divorce" ? COLORS.divorce : COLORS.relation;
      const dash = e.kind === "adopted" ? 'stroke-dasharray="6,5"' : "";
      return `<line x1="${e.x1 - minX}" y1="${e.y1 - minY}" x2="${e.x2 - minX}" y2="${e.y2 - minY}" stroke="${stroke}" stroke-width="2" ${dash}/>`;
    })
    .join("");
  const svgNodes = nodes
    .map((n) => {
      const cx = n.x - minX;
      const cy = n.y - minY;
      const col = personColor(n.person);
      return `<circle cx="${cx}" cy="${cy}" r="${NODE_R / 2}" fill="#FFF" stroke="${col}" stroke-width="3"/>
        <text x="${cx}" y="${cy + 4}" font-size="12" font-weight="bold" fill="${col}" text-anchor="middle">${esc(initials(n.person.name))}</text>
        <text x="${cx}" y="${cy + NODE_R / 2 + 16}" font-size="11" fill="#0F172A" text-anchor="middle">${esc(n.person.name)}</text>`;
    })
    .join("");
  // Responsive SVG: scales to fit its container (sized in mm via CSS) while keeping aspect ratio.
  const tag = `<svg class="treesvg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">${svgEdges}${svgNodes}</svg>`;
  return { tag, nodes };
}

// Print/share the generated HTML (web opens its own window; native prints to a PDF file).
async function outputPdf(html: string, dialogTitle: string) {
  if (Platform.OS === "web") {
    const win = typeof window !== "undefined" ? window.open("", "_blank") : null;
    if (win) {
      win.document.open();
      win.document.write(html);
      win.document.close();
      const fire = () => { try { win.focus(); win.print(); } catch { /* ignore */ } };
      win.onload = fire;
      setTimeout(fire, 700);
      return "web";
    }
  }
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle });
  }
  return uri;
}

export async function exportTreePdf(
  people: Person[],
  relations: Relation[],
  rootId: string | null,
  genUp: number,
  genDown: number,
  appName: string,
  watermark: boolean = false,
) {
  const { tag: svgTag, nodes } = buildTreeSvg(people, relations, rootId, genUp, genDown);

  const rows = [...nodes]
    .sort((a, b) => a.gen - b.gen)
    .map(
      (n) => `<tr>
        <td>${esc(n.person.name)}</td>
        <td>${n.person.gender === "male" ? "L" : n.person.gender === "female" ? "P" : "-"}</td>
        <td>${esc(n.person.birth_date)}</td>
        <td>${esc(n.person.birth_place)}</td>
        <td>${esc(n.person.job)}</td>
        <td>${esc(n.person.death_date)}</td>
        <td>${n.gen > 0 ? "+" : ""}${n.gen}</td>
      </tr>`,
    )
    .join("");

  const html = `<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/>
    <style>
      @page{size:A4 portrait;margin:14mm}
      *{box-sizing:border-box}
      body{font-family:-apple-system,Helvetica,Arial;color:#0F172A;margin:0}
      h1{font-size:22px;margin:0 0 4px}
      h3{font-size:16px;margin:0 0 8px}
      .sub{color:#64748B;font-size:13px;margin-bottom:16px}
      .tree{border:1px solid #E2E8F0;border-radius:12px;padding:10px;margin-bottom:20px;text-align:center;page-break-inside:avoid}
      .treesvg{width:100%;height:150mm;display:block}
      .datasec{page-break-inside:avoid}
      table{width:100%;border-collapse:collapse;font-size:12px}
      th,td{border:1px solid #E2E8F0;padding:6px 8px;text-align:left}
      th{background:#F8FAFC}
      tr{page-break-inside:avoid}
      .wm{position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;
          background:repeating-linear-gradient(-45deg,transparent,transparent 120px,rgba(212,175,55,0.10) 120px,rgba(212,175,55,0.10) 240px);}
      .wmtxt{position:fixed;bottom:6mm;right:8mm;color:#D4AF37;font-size:10px;opacity:0.8}
    </style></head>
    <body>
      ${watermark ? '<div class="wm"></div><div class="wmtxt">Dibuat dengan Titisanku · Paket Gratis</div>' : ""}
      <h1>${esc(appName)}</h1>
      <div class="sub">Pohon Keluarga · ${genUp > 20 ? "Semua leluhur" : `${genUp} generasi ke atas`} · ${genDown > 20 ? "semua keturunan" : `${genDown} generasi ke bawah`} · ${nodes.length} anggota</div>
      <div class="tree">${svgTag}</div>
      <div class="datasec">
        <h3>Data Anggota</h3>
        <table>
          <tr><th>Nama</th><th>JK</th><th>Lahir</th><th>Tempat</th><th>Pekerjaan</th><th>Wafat</th><th>Gen</th></tr>
          ${rows}
        </table>
      </div>
    </body></html>`;

  return outputPdf(html, "Export PDF");
}

// Full family "book": cover + tree page + one profile page per member.
export async function exportTreeBook(
  people: Person[],
  relations: Relation[],
  rootId: string | null,
  appName: string,
  treeName: string,
) {
  const { tag: svgTag } = buildTreeSvg(people, relations, rootId, 99, 99);
  const today = new Date().toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" });

  const ordered = [...people].sort((a, b) => {
    if (a.is_root && !b.is_root) return -1;
    if (b.is_root && !a.is_root) return 1;
    return a.name.localeCompare(b.name);
  });

  const gender = (g?: string | null) => (g === "male" ? "Laki-laki" : g === "female" ? "Perempuan" : "-");
  const lifespan = (p: Person) => `${p.birth_date || "?"}${p.death_date ? ` – ${p.death_date}` : ""}`;

  const profiles = ordered
    .map((p) => {
      const photo = fileUrl(p.photo_url);
      const avatar = photo
        ? `<img class="ava" src="${photo}"/>`
        : `<div class="ava avatxt" style="border-color:${personColor(p)};color:${personColor(p)}">${esc(initials(p.name))}</div>`;
      return `<section class="page profile">
        <div class="pcard">
          ${avatar}
          <h2>${esc(p.name)}${p.is_root ? ' <span class="badge">Pusat</span>' : ""}</h2>
          <table class="pinfo">
            <tr><td>Jenis Kelamin</td><td>${gender(p.gender)}</td></tr>
            <tr><td>Tanggal Lahir</td><td>${esc(p.birth_date)}</td></tr>
            <tr><td>Tempat Lahir</td><td>${esc(p.birth_place)}</td></tr>
            <tr><td>Pekerjaan</td><td>${esc(p.job)}</td></tr>
            <tr><td>Wafat</td><td>${p.death_date ? esc(p.death_date) : "-"}</td></tr>
            <tr><td>Rentang Hidup</td><td>${esc(lifespan(p))}</td></tr>
          </table>
          ${p.notes ? `<div class="notes"><div class="nlabel">Catatan</div><div>${esc(p.notes)}</div></div>` : ""}
        </div>
      </section>`;
    })
    .join("");

  const html = `<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/>
    <style>
      @page{size:A4 portrait;margin:14mm}
      *{box-sizing:border-box}
      body{font-family:Georgia,'Times New Roman',serif;color:#1F2A44;margin:0}
      .page{page-break-after:always}
      .cover{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
             min-height:250mm;background:linear-gradient(160deg,#FFFBF0,#F3EAD6);}
      .cover .crest{font-size:64px;margin-bottom:12px}
      .cover h1{font-size:40px;margin:0 0 8px;letter-spacing:1px}
      .cover .tname{font-size:24px;color:#8A6D2F;margin:0 0 24px}
      .cover .meta{color:#64748B;font-size:14px}
      .cover .rule{width:120px;height:3px;background:#D4AF37;margin:20px 0;border-radius:2px}
      .treepage h2{font-size:22px;text-align:center;margin:0 0 16px}
      .tree{border:1px solid #E2E8F0;border-radius:12px;padding:12px;text-align:center;page-break-inside:avoid}
      .treesvg{width:100%;height:210mm;display:block}
      .profile{page-break-inside:avoid}
      .profile .pcard{border:1px solid #EADFC5;border-radius:16px;padding:28px;max-width:620px;margin:0 auto}
      .ava{width:130px;height:130px;border-radius:999px;object-fit:cover;display:block;margin:0 auto 16px;border:4px solid #D4AF37}
      .avatxt{display:flex;align-items:center;justify-content:center;font-size:44px;font-weight:bold;background:#FFF;border-width:4px;border-style:solid}
      .profile h2{text-align:center;font-size:26px;margin:0 0 20px}
      .badge{font-size:12px;background:#D4AF37;color:#fff;padding:2px 8px;border-radius:999px;vertical-align:middle}
      table.pinfo{width:100%;border-collapse:collapse;font-family:Helvetica,Arial;font-size:14px}
      table.pinfo td{padding:9px 6px;border-bottom:1px solid #EEE}
      table.pinfo td:first-child{color:#8A6D2F;width:42%;font-weight:600}
      .notes{margin-top:18px;font-family:Helvetica,Arial;font-size:14px;line-height:1.5}
      .notes .nlabel{color:#8A6D2F;font-weight:700;margin-bottom:4px}
    </style></head>
    <body>
      <section class="page cover">
        <div class="crest">🌳</div>
        <h1>Buku Silsilah</h1>
        <div class="tname">${esc(treeName)}</div>
        <div class="rule"></div>
        <div class="meta">${people.length} anggota keluarga<br/>Dicetak ${today}<br/>${esc(appName)}</div>
      </section>
      <section class="page treepage">
        <h2>Pohon Keluarga</h2>
        <div class="tree">${svgTag}</div>
      </section>
      ${profiles}
    </body></html>`;

  return outputPdf(html, "Buku Silsilah");
}
