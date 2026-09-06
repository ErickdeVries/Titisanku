import { Person, Relation } from "@/src/api";

export const NODE_D = 64; // node diameter
export const NODE_R = NODE_D / 2;
const COL_W = 120;
const ROW_H = 160;
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

  // BFS to assign generations
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

  // limit visible generations relative to focus (focus = gen 0)
  for (const [nid, g] of [...gen.entries()]) {
    if (g < -genUp || g > genDown) gen.delete(nid);
  }

  // group by generation
  const byGen = new Map<number, string[]>();
  for (const [id, g] of gen.entries()) {
    if (!byGen.has(g)) byGen.set(g, []);
    byGen.get(g)!.push(id);
  }
  // keep spouses adjacent: reorder each gen so spouses sit next to each other
  for (const [g, ids] of byGen.entries()) {
    const ordered: string[] = [];
    const seen = new Set<string>();
    for (const id of ids) {
      if (seen.has(id)) continue;
      ordered.push(id);
      seen.add(id);
      for (const sp of spousesOf(id)) {
        if (gen.get(sp) === g && !seen.has(sp)) {
          ordered.push(sp);
          seen.add(sp);
        }
      }
    }
    byGen.set(g, ordered);
  }

  const gens = Array.from(byGen.keys()).sort((a, b) => a - b);
  const minGen = gens[0];
  const maxCount = Math.max(...gens.map((g) => byGen.get(g)!.length));
  const width = maxCount * COL_W + PAD * 2;

  const nodes: LayoutNode[] = [];
  const posById = new Map<string, { x: number; y: number }>();
  for (const g of gens) {
    const ids = byGen.get(g)!;
    const n = ids.length;
    const startX = (width - n * COL_W) / 2 + COL_W / 2;
    const y = PAD + (g - minGen) * ROW_H + NODE_R;
    ids.forEach((id, i) => {
      const x = startX + i * COL_W;
      posById.set(id, { x, y });
      nodes.push({ id, person: byId.get(id)!, x, y, gen: g });
    });
  }
  const height = PAD * 2 + (gens.length - 1) * ROW_H + NODE_D;

  const edges: LayoutEdge[] = [];
  for (const r of relations) {
    const a = posById.get(r.person_id);
    const b = posById.get(r.related_person_id);
    if (!a || !b) continue;
    if (PARENT_TYPES.includes(r.relation_type)) {
      // parent (person_id) -> child (related_person_id)
      edges.push({
        key: r.id,
        x1: a.x,
        y1: a.y + NODE_R,
        x2: b.x,
        y2: b.y - NODE_R,
        kind: r.relation_type === "adopted_child" ? "adopted" : "relation",
      });
    } else if (SPOUSE_TYPES.includes(r.relation_type)) {
      edges.push({
        key: r.id,
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        kind: r.relation_type === "divorced" ? "divorce" : "spouse",
      });
    } else if (SIBLING_TYPES.includes(r.relation_type)) {
      edges.push({
        key: r.id,
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        kind: "relation",
      });
    }
  }

  return { nodes, edges, width, height };
}
