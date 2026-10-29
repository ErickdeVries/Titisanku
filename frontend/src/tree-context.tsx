import React, { createContext, useContext, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { storage } from "@/src/utils/storage";
import { listTrees, setActiveTree as setApiTree, Tree } from "@/src/api";
import { useAuth } from "@/src/auth";

const ACTIVE_KEY = "active_tree_id";

type TreeCtx = {
  trees: Tree[];
  activeTree: Tree | null;
  activeTreeId: string | null;
  loading: boolean;
  setActive: (id: string) => Promise<void>;
  refreshTrees: () => Promise<Tree[]>;
  clearTree: () => void;
  pendingFocusId: string | null;
  setPendingFocus: (id: string | null) => void;
};

const Ctx = createContext<TreeCtx>({
  trees: [],
  activeTree: null,
  activeTreeId: null,
  loading: true,
  setActive: async () => {},
  refreshTrees: async () => [],
  clearTree: () => {},
  pendingFocusId: null,
  setPendingFocus: () => {},
});

export function TreeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [trees, setTrees] = useState<Tree[]>([]);
  const [activeTreeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingFocusId, setPendingFocusId] = useState<string | null>(null);
  const setPendingFocus = useCallback((id: string | null) => setPendingFocusId(id), []);
  // User id the current tree data was loaded for — used to reset stale state
  // when the signed-in account changes.
  const loadedFor = useRef<string | null | undefined>(undefined);

  const applyActive = useCallback(
    async (id: string | null) => {
      setApiTree(id);
      setActiveId(id);
      if (id) await storage.setItem(ACTIVE_KEY, id);
    },
    [],
  );

  const refreshTrees = useCallback(async (): Promise<Tree[]> => {
    const list = await listTrees();
    setTrees(list);
    return list;
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    try {
      const list = await refreshTrees();
      const stored = await storage.getItem<string>(ACTIVE_KEY, "");
      const chosen = list.find((t) => t.id === stored) || list[0] || null;
      await applyActive(chosen ? chosen.id : null);
    } catch (e) {
      console.log("tree bootstrap error", e);
    } finally {
      setLoading(false);
    }
  }, [refreshTrees, applyActive]);

  // Logout / user switch: reset immediately so no stale tree from the previous
  // account is visible while the new session bootstraps. Exposed for callers
  // that need to force a reload of the list.
  const clearTree = useCallback(() => {
    setApiTree(null);
    setActiveId(null);
    setTrees([]);
  }, []);

  const userId = user?.user_id ?? null;

  // Load the tree list whenever the signed-in account changes. Done during
  // render (React's "adjust state when props change" pattern) instead of inside
  // an effect, so the previous account's tree is dropped synchronously and no
  // extra render pass is needed.
  if (loadedFor.current !== userId) {
    loadedFor.current = userId;
    clearTree();
    if (userId) {
      setTimeout(bootstrap, 0);
    } else {
      setLoading(false);
    }
  }

  const setActive = useCallback(
    async (id: string) => {
      await applyActive(id);
      await qc.invalidateQueries();
    },
    [applyActive, qc],
  );

  const activeTree = trees.find((t) => t.id === activeTreeId) || null;

  return (
    <Ctx.Provider value={{ trees, activeTree, activeTreeId, loading, setActive, refreshTrees, clearTree, pendingFocusId, setPendingFocus }}>
      {children}
    </Ctx.Provider>
  );
}

export const useTree = () => useContext(Ctx);
