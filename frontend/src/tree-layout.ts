import { Person, Relation } from "@/src/api";

export const NODE_D = 64; // node diameter
export const NODE_R = NODE_D / 2;
const COL_W = 128; // horizontal slot width
const ROW_H = 168; // vertical distance between generations
const PAD = 60;

export type LayoutNode = {
  id: string;
  person: Person;
  x: number; // center x
  y: number; // center y
  gen: number;
};

export type LayoutEdge = {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  kind: "relation" | "adopted" | "spouse" | "divorce";
  orient: "v" | "h";
};

export type TreeLayout = {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  width: number;
  height: number;
};

const PARENT_TYPES = ["parent", "adopted_child"];
const SPOUSE_TYPES = ["spouse", "divorced"];
const SIBLING_TYPES = ["sibling"];

/**
 * Parent-centered ("tidy") family tree layout.
 * - The whole visible set descends from the top-most visible ancestors, so it renders
 *   as one downward org-chart (ancestors on top, focus in the middle, descendants below).
 * - Couples are merged into a "unit" and placed side by side.
 * - Each family's children are placed directly beneath (and centered under) their parents,
 *   connected with a clean stem → horizontal bus → vertical drop connector. This prevents
 *   the tangled cross-generation lines.
 */
export function buildLayout(
  people: Person[],
  relations: Relation[],
  focusId: string | null,
  genUp: number = Infinity,
  genDown: number = Infinity,
): TreeLayout {
  const byId = new Map(people.map((p) => [p.id, p]));
  const start = focusId && byId.has(focusId) ? focusId : people[0]?.id;
  if (!start) return { nodes: [], edges: [], width: 0, height: 0 };

  const childrenOf = (id: string) =>
    relations.filter((r) => r.person_id === id && PARENT_TYPES.includes(r.relation_type)).map((r) => r.related_person_id);
  const parentsOf = (id: string) =>
    relations.filter((r) => r.related_person_id === id && PARENT_TYPES.includes(r.relation_type)).map((r) => r.person_id);
  const spousesOf = (id: string) =>
    relations
      .filter((r) => SPOUSE_TYPES.includes(r.relation_type) && (r.person_id === id || r.related_person_id === id))
      .map((r) => (r.person_id === id ? r.related_person_id : r.person_id));
  const siblingsOf = (id: string) =>
    relations
      .filter((r) => SIBLING_TYPES.includes(r.relation_type) && (r.person_id === id || r.related_person_id === id))
      .map((r) => (r.person_id === id ? r.related_person_id : r.person_id));

  // BFS to assign generations relative to focus (focus = 0)
  const gen = new Map<string, number>();
  const queue: string[] = [start];
  gen.set(start, 0);
  while (queue.length) {
    const id = queue.shift()!;
    const g = gen.get(id)!;
    const neighbors: [string, number][] = [];
    parentsOf(id).forEach((p) => neighbors.push([p, g - 1]));
    childrenOf(id).forEach((c) => neighbors.push([c, g + 1]));
    spousesOf(id).forEach((s) => neighbors.push([s, g]));
    siblingsOf(id).forEach((s) => neighbors.push([s, g]));
    for (const [nid, ng] of neighbors) {
      if (!byId.has(nid)) continue;
      if (!gen.has(nid)) {
        gen.set(nid, ng);
        queue.push(nid);
      }
    }
  }

  // limit visible generations relative to focus
  for (const [nid, g] of [...gen.entries()]) {
    if (g < -genUp || g > genDown) gen.delete(nid);
  }

  const vis = (id: string) => gen.has(id);
  const parentsIn = (id: string) => parentsOf(id).filter(vis).sort();
  const spouseIn = (id: string) => spousesOf(id).filter((s) => vis(s) && gen.get(s) === gen.get(id));

  // ---- Build units (a couple merged, or a single person) ----
  type Unit = { members: string[]; primary: string; gen: number; x: number };
  const units: Unit[] = [];
  const unitOf = new Map<string, number>();
  const seen = new Set<string>();
  for (const p of people) {
    const id = p.id;
    if (!vis(id) || seen.has(id)) continue;
    const members = [id];
    seen.add(id);
    const sp = spouseIn(id).find((s) => !seen.has(s));
    if (sp) {
      members.push(sp);
      seen.add(sp);
    }
    // primary member = the blood descendant (the one with visible parents)
    let primary = id;
    if (parentsIn(id).length === 0 && sp && parentsIn(sp).length > 0) primary = sp;
    const idx = units.length;
    units.push({ members, primary, gen: gen.get(id)!, x: 0 });
    members.forEach((m) => unitOf.set(m, idx));
  }

  // ---- Parent unit for each unit ----
  const parentUnit = new Array(units.length).fill(-1);
  units.forEach((u, i) => {
    const pnode = parentsIn(u.primary)[0];
    if (pnode != null && unitOf.has(pnode)) parentUnit[i] = unitOf.get(pnode)!;
  });

  const birthKey = (id: string) => byId.get(id)?.birth_date || "9999-99-99";
  const childUnitsOf = (i: number) =>
    units
      .map((_, j) => j)
      .filter((j) => parentUnit[j] === i)
      .sort((a, b) => {
        const ka = birthKey(units[a].primary);
        const kb = birthKey(units[b].primary);
        if (ka !== kb) return ka < kb ? -1 : 1;
        return (byId.get(units[a].primary)?.name || "").localeCompare(byId.get(units[b].primary)?.name || "");
      });

  // ---- Measure subtree widths (in slots), then place ----
  const wOf = new Array(units.length).fill(0);
  const measure = (i: number): number => {
    const kids = childUnitsOf(i);
    const own = units[i].members.length;
    if (!kids.length) {
      wOf[i] = own;
      return own;
    }
    let cw = 0;
    for (const k of kids) cw += measure(k);
    wOf[i] = Math.max(own, cw);
    return wOf[i];
  };
  const place = (i: number, left: number) => {
    const kids = childUnitsOf(i);
    if (!kids.length) {
      units[i].x = left + (wOf[i] - 1) / 2;
      return;
    }
    let cw = 0;
    for (const k of kids) cw += wOf[k];
    let cx = left + (wOf[i] - cw) / 2;
    for (const k of kids) {
      place(k, cx);
      cx += wOf[k];
    }
    const first = kids[0];
    const last = kids[kids.length - 1];
    units[i].x = (units[first].x + units[last].x) / 2;
  };

  const roots = units
    .map((_, i) => i)
    .filter((i) => parentUnit[i] === -1)
    .sort((a, b) => units[a].gen - units[b].gen);
  let cursor = 0;
  for (const r of roots) {
    measure(r);
    place(r, cursor);
    cursor += wOf[r];
  }
  const totalSlots = Math.max(cursor, 1);

  // ---- Pixel coordinates ----
  const gensSorted = [...new Set(units.map((u) => u.gen))].sort((a, b) => a - b);
  const minGen = gensSorted[0] ?? 0;
  const genY = (g: number) => PAD + (g - minGen) * ROW_H + NODE_R;
  const slotX = (s: number) => PAD + NODE_R + s * COL_W;

  const posById = new Map<string, { x: number; y: number }>();
  const nodes: LayoutNode[] = [];
  for (const u of units) {
    const y = genY(u.gen);
    const m = u.members.length;
    u.members.forEach((mid, k) => {
      const sx = u.x - (m - 1) / 2 + k;
      const x = slotX(sx);
      posById.set(mid, { x, y });
      nodes.push({ id: mid, person: byId.get(mid)!, x, y, gen: u.gen });
    });
  }

  const width = PAD * 2 + NODE_D + totalSlots * COL_W;
  const height = PAD * 2 + NODE_D + (gensSorted.length - 1) * ROW_H;

  // ---- Edges ----
  const edges: LayoutEdge[] = [];
  const mk = (
    key: string,
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    kind: LayoutEdge["kind"],
    orient: LayoutEdge["orient"],
  ) => edges.push({ key, x1, y1, x2, y2, kind, orient });

  // Family connectors: stem down from the couple, a bus spanning the children, drops to each child.
  units.forEach((u, i) => {
    const kids = childUnitsOf(i);
    if (!kids.length) return;
    const parentBottom = genY(u.gen) + NODE_R;
    const childTop = genY(u.gen + 1) - NODE_R;
    const busY = (parentBottom + childTop) / 2;
    const stemX = slotX(u.x);
    const dropXs = kids.map((k) => posById.get(units[k].primary)!.x);
    // stem
    mk(`fam-${i}-stem`, stemX, parentBottom, stemX, busY, "relation", "v");
    // horizontal bus (include stem so it always connects)
    const minX = Math.min(stemX, ...dropXs);
    const maxX = Math.max(stemX, ...dropXs);
    if (maxX - minX > 0.5) mk(`fam-${i}-bus`, minX, busY, maxX, busY, "relation", "h");
    // drops
    kids.forEach((k, ki) => {
      const c = units[k].primary;
      const adopted = relations.some(
        (r) => r.related_person_id === c && u.members.includes(r.person_id) && r.relation_type === "adopted_child",
      );
      mk(`fam-${i}-drop-${k}`, dropXs[ki], busY, dropXs[ki], childTop, adopted ? "adopted" : "relation", "v");
    });
  });

  // Spouse / divorce lines within a couple (short horizontal segment)
  units.forEach((u, i) => {
    if (u.members.length < 2) return;
    const a = posById.get(u.members[0])!;
    const b = posById.get(u.members[1])!;
    const rel = relations.find(
      (r) =>
        SPOUSE_TYPES.includes(r.relation_type) &&
        ((r.person_id === u.members[0] && r.related_person_id === u.members[1]) ||
          (r.person_id === u.members[1] && r.related_person_id === u.members[0])),
    );
    const kind = rel && rel.relation_type === "divorced" ? "divorce" : "spouse";
    mk(`sp-${i}`, a.x, a.y, b.x, b.y, kind, "h");
  });

  // Secondary parent relations (a parent that is NOT the child's primary parent-unit) → elbow
  const drawnPrimary = new Set<string>();
  units.forEach((u, i) => {
    childUnitsOf(i).forEach((k) => drawnPrimary.add(`${i}->${units[k].primary}`));
  });
  for (const r of relations) {
    if (!PARENT_TYPES.includes(r.relation_type)) continue;
    const par = r.person_id;
    const ch = r.related_person_id;
    if (!vis(par) || !vis(ch)) continue;
    const pu = unitOf.get(par);
    if (pu == null) continue;
    if (drawnPrimary.has(`${pu}->${ch}`)) continue; // already drawn by family connector
    const a = posById.get(par);
    const b = posById.get(ch);
    if (!a || !b) continue;
    const midY = (a.y + NODE_R + (b.y - NODE_R)) / 2;
    const kind = r.relation_type === "adopted_child" ? "adopted" : "relation";
    mk(`sec-${r.id}-a`, a.x, a.y + NODE_R, a.x, midY, kind, "v");
    mk(`sec-${r.id}-b`, a.x, midY, b.x, midY, kind, "h");
    mk(`sec-${r.id}-c`, b.x, midY, b.x, b.y - NODE_R, kind, "v");
  }

  // Explicit sibling relations with no shared parents (rare) → light horizontal
  for (const r of relations) {
    if (!SIBLING_TYPES.includes(r.relation_type)) continue;
    const a = posById.get(r.person_id);
    const b = posById.get(r.related_person_id);
    if (!a || !b) continue;
    mk(`sib-${r.id}`, a.x, a.y, b.x, b.y, "relation", "h");
  }

  return { nodes, edges, width, height };
}
