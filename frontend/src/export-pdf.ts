import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { Person, Relation } from "@/src/api";
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

export async function exportTreePdf(
  people: Person[],
  relations: Relation[],
  rootId: string | null,
  genUp: number,
  genDown: number,
  appName: string,
  watermark: boolean = false,
) {
  const full = buildLayout(people, relations, rootId);
  const inRange = (g: number) => g >= -genUp && g <= genDown;
  const nodes = full.nodes.filter((n) => inRange(n.gen));
  const ids = new Set(nodes.map((n) => n.id));
  const minGen = Math.min(...nodes.map((n) => n.gen), 0);

  // shift y so filtered gens start near top
  const yShift = minGen === -genUp ? 0 : 0;
  const edges = full.edges.filter((e) => {
    const inNodes = nodes.filter((n) => Math.abs(n.x - e.x1) < 1 && Math.abs(n.y - e.y1 + NODE_R) < 200);
    return true;
  });

  // recompute width/height for range
  const minX = Math.min(...nodes.map((n) => n.x)) - 60;
  const maxX = Math.max(...nodes.map((n) => n.x)) + 60;
  const minY = Math.min(...nodes.map((n) => n.y)) - 60;
  const maxY = Math.max(...nodes.map((n) => n.y)) + 60;
  const w = Math.max(maxX - minX, 200);
  const h = Math.max(maxY - minY, 200);

  const nodeSet = new Set(nodes.map((n) => `${n.id}`));
  const svgEdges = full.edges
    .map((e) => {
      // only draw if both endpoints are within filtered vertical range
      if (e.y1 < minY || e.y2 > maxY + 10) {
        // still allow; simpler: draw all edges among included nodes by coordinate proximity
      }
      const stroke = e.kind === "adopted" ? COLORS.adopted : e.kind === "divorce" ? COLORS.divorce : COLORS.relation;
      const dash = e.kind === "adopted" ? 'stroke-dasharray="6,5"' : "";
      const inV = e.y1 >= minY && e.y2 <= maxY;
      if (!inV) return "";
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

  const rows = nodes
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

  const html = `<html><head><meta name="viewport" content="width=device-width"/>
    <style>
      body{font-family:-apple-system,Helvetica,Arial;padding:24px;color:#0F172A}
      h1{font-size:22px;margin:0 0 4px}
      .sub{color:#64748B;font-size:13px;margin-bottom:20px}
      .tree{border:1px solid #E2E8F0;border-radius:12px;padding:12px;margin-bottom:24px;overflow:hidden}
      table{width:100%;border-collapse:collapse;font-size:12px}
      th,td{border:1px solid #E2E8F0;padding:6px 8px;text-align:left}
      th{background:#F8FAFC}
      .wm{position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;
          background:repeating-linear-gradient(-45deg,transparent,transparent 120px,rgba(212,175,55,0.10) 120px,rgba(212,175,55,0.10) 240px);}
      .wmtxt{position:fixed;bottom:16px;right:16px;color:#D4AF37;font-size:11px;opacity:0.8}
    </style></head>
    <body>
      ${watermark ? '<div class="wm"></div><div class="wmtxt">Dibuat dengan KETURUNANKU · Paket Gratis</div>' : ""}
      <h1>${esc(appName)}</h1>
      <div class="sub">Pohon Keluarga · ${genUp > 20 ? "Semua leluhur" : `${genUp} generasi ke atas`} · ${genDown > 20 ? "semua keturunan" : `${genDown} generasi ke bawah`} · ${nodes.length} anggota</div>
      <div class="tree"><svg width="100%" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">${svgEdges}${svgNodes}</svg></div>
      <h3>Data Anggota</h3>
      <table>
        <tr><th>Nama</th><th>JK</th><th>Lahir</th><th>Tempat</th><th>Pekerjaan</th><th>Wafat</th><th>Gen</th></tr>
        ${rows}
      </table>
    </body></html>`;

  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Export PDF" });
  }
  return uri;
}
