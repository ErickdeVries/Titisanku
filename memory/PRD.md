# KETURUNANKU — Product Requirements

## Original Problem
Mobile app to record family genealogy (silsilah keluarga). React Native + Expo + FastAPI +
MongoDB. Interactive zoomable/pannable family-tree canvas with 4-direction node generation,
full person form (multi-tab), search, PDF export, birthday reminders, multi-language (ID/EN),
JSON backup, and email collaboration invites. Google login; first user = admin + root node.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor).
  Collections: `users`, `people`, `relations`, `user_sessions`, `invites`, `meta`.
- Auth: Emergent-managed Google OAuth (session_token, 7-day). First user → admin + root person.
- Storage: Emergent Object Storage for person photos (`/api/upload`, `/api/files/{path}`).
- Email: Emergent-managed Resend for collaboration invites.
- Frontend: Expo Router. Tabs: Tree / Search / Add / Settings. Poppins font, white bg,
  gradient CTAs. Tree canvas uses react-native-gesture-handler + reanimated + react-native-svg.

## User Personas
- Family historian (admin): builds and maintains the tree, invites relatives.
- Contributing relative (editor): adds/edits people.
- Viewer: browses the tree.

## Core Requirements (static)
- 3 tables: users(role), people, relations(parent/child/spouse/divorced/adopted_child).
- Zoom/pan SVG tree from root; circular photo nodes; color by gender/admin; line styles
  (solid=blood/marriage, dashed=adopted, red=divorce).
- 4-direction add (+Ayah/+Ibu/+Pasangan/+Anak), unlimited generations.
- Person form: name, gender, photo, birth/death date, birth place, job, notes;
  Marriage/Divorce tabs; Adopted checkbox.
- Search, PDF export (generation range), birthday local notifications (living only),
  ID/EN toggle, JSON backup, email invites + manual code.

## Implemented (2026-06)
- [x] DB schema + all CRUD endpoints, RBAC (admin/editor/viewer) — tested 22/22 pass.
- [x] Google OAuth login; first user admin+root auto-created.
- [x] Tree canvas: pinch zoom, pan, colored nodes, relation/adopted/divorce lines, legend.
- [x] Node selection → 4-direction add buttons → modal PersonForm → auto tree update.
- [x] PersonForm with General/Marriage/Divorce tabs, photo upload (Object Storage), date pickers.
- [x] Person detail (view/edit/delete + quick add), Search tab, Add tab (target + direction).
- [x] Settings: ID/EN toggle, birthday reminders toggle, JSON backup, invite (admin) / join code (viewer), logout.
- [x] PDF export with generation range (SVG tree diagram + data table).
- [x] Photo upload + authenticated download verified through Object Storage.
- [x] Focus/re-center tree on ANY selected person (crosshair button + "back to root" chip).
- [x] Marriage/divorce dates shown on spouse relations in person detail (PERNIKAHAN card).
- [x] Family stats strip on tree (members, generations, nearest birthday).
- [x] Restore backup: admin imports JSON file to restore whole tree (tested end-to-end).

## Backlog / Next
- P2: Node de-overlap layout for very wide generations.
- P2: Offline caching of tree.
- P2: Multiple spouses ordering refinement in layout.

## Notes
- Birthday reminders + image picker require a native/dev build to fully test (not Expo Go web).
- DO NOT wipe the shared preview DB in future iterations — the user's real data lives there. Earlier
  end-of-iteration `delete_many({})` wipes caused the "data tidak tersimpan" report. For tests, seed and
  remove ONLY the synthetic docs you created.

## Iteration 3 — Chat, Notes, Files, Notifications (2026-06)
- Collections added: `person_notes` (id, person_id, author_id, author_name, note_text, attachments[], created_at, deleted_at),
  `family_chat` (id, room_id=admin user_id, sender_id, message, attachments[], reply_to snapshot, created_at, deleted_at),
  `app_notifications` (id, user_id recipient, type[chat|note|file], title, body, read, created_at).
- `people.notes` column already existed (personal note) — unchanged.
- Endpoints: GET/POST /api/people/{id}/notes, POST /api/people/{id}/files, GET/POST /api/chat,
  GET /api/notifications, POST /api/notifications/read?type=. /api/tree now returns note_count per person.
- UI: Person detail tabs Data/Catatan/File; new Chat tab (WhatsApp-style, reply + photo, admin/editor send, viewer read-only);
  unread chat badge on Chat tab; yellow dot on tree nodes that have notes.
- RBAC + notification fan-out verified by testing_agent: 27/27 pass.

## Iteration 4 — Multi-Tenant SaaS Pivot + Modern Heritage (2026-06)
### Backend (server.py) — tested 27/27 pass
- New collections: `trees` {id,name,owner_id,plan(free|pro),root_person_id,created_at},
  `tree_members` {id,tree_id,user_id,role(admin|editor|viewer),joined_at}.
- `tree_id` added to people/relations/family_chat/person_notes/app_notifications.
- All data endpoints tenant-scoped via `resolve_tree(user, tree_id)`; role now per-tree.
- Non-destructive startup migration `migrate_multitenant` (idempotent, meta flag). Fresh DB = no-op.
- Every new Google user auto-gets their own tree (admin) with a root person.
- Subscription: Free plan capped at FREE_PERSON_LIMIT=50 people. add-relative returns 402
  "LIMIT_REACHED:..." when full. POST /trees/{id}/upgrade sets plan=pro (admin only).
- New endpoints: GET/POST /trees, GET /trees/{id}/members, PUT /trees/{id}/members/role,
  DELETE /trees/{id}/members/{member_id}, POST /trees/{id}/upgrade.
- backup/restore/chat/notes all tree-scoped.
### Frontend
- Modern Heritage theme (theme.ts): Gold #D4AF37, Royal Blue #1E3A8A, Cream #FFFBF0 bg,
  Playfair Display display font (assets/fonts), gold->blue brandGradient, lucide-react-native icons.
- api.ts auto-injects ?tree_id via setActiveTree; new tree/member/subscription API fns.
- src/tree-context.tsx: active tree state (persisted), TreeProvider in _layout.
- Bottom nav changed to [Pohon][Chat][Cari][Profil] (add tab hidden). lucide icons.
- New screens: app/trees.tsx (switcher + create), app/subscription.tsx (plan + upgrade),
  app/members.tsx (admin role change / remove). UpgradeModal component gates add at limit.
- Tree header shows active tree name + plan chip + count; Profil screen links to all three.
- NOTE: Upgrade currently activates Pro directly (MVP). Midtrans payment = pending (Phase 3).

## Remaining backlog (from Message 354)
- P1: Tree invitation via link (join as editor into tree_members / create own tree).
- P1: Chat — edit sent message, tap reply to jump, per-member unread badges.
- P2: Midtrans payment for Pro upgrade (chosen by user).
- P2: PDF watermark on Free; Backup to Google Drive (Pro, needs GDrive integration).
- P2: Node "grow" animation from parent to child on add.

## Iteration 5 — Siblings + Hybrid Explorer (2026-06)
- Backend: add-relative supports direction "sibling". Shares focus's parents (links new person
  as child of every parent); if focus has no parents, creates explicit relation_type "sibling".
  Verified by test_sibling.py (3/3). delete_person soft-deletes sibling relations too.
- tree-layout.ts understands "sibling" (same generation + connector edge).
- Explorer (Hybrid, user-chosen): app/explorer/[id].tsx — drill-down card view. Sections
  Orang Tua / Center+Pasangan / Saudara (Kakak left, Adik right, sorted by birth_date) / Anak.
  Big photo cards (src/components/BigPersonCard.tsx), pinch + +/- zoom, tap card = push new
  explorer page (stack/back), info button = person detail, contextual +add chips for editors.
- Entry points: compass button in Tree header + person detail header. Tree canvas gained a
  6th add button (Saudara). add.tsx & person detail quick-actions gained Kakak/Adik.
- Role checks in index/add/person-detail now use per-tree role (data.role) with user.role fallback.
- Verified via screenshots: Explorer + Tree canvas render correctly with Modern Heritage theme.

## Iteration 6 — Invite Links + Generation Filter (2026-06)
- Backend (tested: invite 8/8, sibling 3/3, no regressions):
  - Collection `tree_invites` {id,tree_id,token,role:editor,created_by,active}.
  - POST /trees/{tid}/invite-link (admin, reuses active link), GET /invite-info/{token} (auth),
    POST /invite-accept/{token} (adds caller as editor member, idempotent).
- Frontend:
  - members.tsx: admin "Buat Link Undangan" → copy (expo-clipboard) / share (Share). Link =
    origin/invite/{token} (web) or Linking.createURL (native).
  - app/invite/[token].tsx: if logged out → store pending_invite + Google login; after login
    RootNav resumes to /invite/{token}. If logged in → shows inviter + tree, "Gabung sebagai
    Editor" (accept) or "Buat Pohon Baru Milik Saya". RootNav allows /invite unauthenticated.
  - Generation filter: buildLayout(people,relations,focus,genUp,genDown) filters nodes by signed
    generation distance from focus. Tree canvas: "sliders" header button → Filter Generasi modal
    (steppers, default 2/2, "Tampilkan Semua"=99). Explorer: per-page depth steppers (0-2) that
    reveal Kakek/Nenek (2 up) and Cucu (2 down) sections.
- All verified via screenshots (Explorer depth, Members invite, Invite landing, Filter modal).

## Iteration 7 — Plan tiers, 1-tree-per-account, auto relations (2026-06)
- Plans: free/pro/family. Limits people(50/∞/∞), editors(3/10/50), photos(20/∞/∞). 402 codes:
  LIMIT_REACHED (people), EDITOR_LIMIT, PHOTO_LIMIT. Payment = SIMULATION (Midtrans pending key).
- Subscription screen shows 3 tiers + usage (orang/editor/foto). UpgradeModal exact copy +
  [Upgrade Sekarang]->/subscription + [Tanya ke Admin]. PDF watermark when plan=free.
  Settings: "Backup ke Google Drive" visible for pro/family (function deferred).
- 1 TREE PER ACCOUNT: removed Add/Switch tree UI (header name non-tappable, settings row gone,
  invite screen keeps only "Gabung sebagai Editor"). TreeProvider still resolves the primary/active
  tree internally (persisted), so invited editors stay on the joined tree.
- Auto family relations on person detail: computes Ayah/Ibu/Kakek/Nenek/Saudara/Anak from graph,
  each tappable + deletable (admin/editor) via new DELETE /relations/{rel_id}. All person fields
  editable via existing edit form.
- Backend tested: plan limits, family upgrade, editor limit 402, relation delete + viewer 403.

## Iteration 8 — Editable marriage dates (DD/MM/YYYY), duplicate-parent fix, tree readability (2026-06)
- DateField (src/components/DateField.tsx): masked DD/MM/YYYY text input, stores ISO internally.
  Replaced old native/web DateField inside PersonForm (birth/death/marriage/divorce all use it).
- NEW backend PUT /api/relations/{rel_id}: edit marriage_date/divorce_date/is_divorced on a spouse
  relation (toggles relation_type spouse<->divorced, clears divorce_date when not divorced). admin/editor
  only; 400 for non-spouse rel, 404 unknown. Person detail "Info Pernikahan" card gained an edit pencil
  (spouse-edit-<relId>) opening a modal (edit-marriage-date/edit-divorce-date/edit-divorced-toggle).
  Dates now render DD/MM/YYYY via isoToDisplay.
- DUPLICATE-PARENT FIX: add-relative direction=child now auto-links the child to the focus's spouse when
  the focus has EXACTLY ONE spouse (both parents attach; no more manually-created duplicate mother).
  0 spouses -> 1 parent; 2+ spouses -> no auto-link (ambiguous). Verified 13/13 backend tests.
- NAVIGATION: person detail "Jadikan Pusat Pohon" (set-as-root) sets tree-context pendingFocus and
  navigates to Tree tab which focuses that person. tree-context gained pendingFocusId/setPendingFocus.
- TREE READABILITY (design agent blueprint /app/design_guidelines.json): parent->child edges now use
  orthogonal ELBOW routing (react-native-svg Path) instead of straight diagonals; spouse/sibling stay
  horizontal Lines. Spacing COL_W 128 / ROW_H 164. Filter panel reworded: "Filter Tampilan Pohon",
  "Pusat saat ini: <nama>", "Generasi Leluhur (Ke atas)/Keturunan (Ke bawah)", "Terapkan Filter".
  Export modal now exports the CURRENT filtered view (activeFocus + filterUp/filterDown) with a summary,
  no separate gen steppers.
- Tested by testing_agent: 13/13 backend PASS + frontend flows verified. No functional bugs.

## Iteration 8b — Parent-centered (tidy) tree layout rewrite (2026-06)
- User feedback: tree still "semrawut" — lines connected everywhere within a generation because
  children were laid out in a flat centered row (NOT under their parents), so the parent→child
  "bus" and spouse lines sprawled across the whole generation.
- Rewrote src/tree-layout.ts buildLayout into a proper tidy/org-chart layout:
  - Couples merged into "units"; whole visible set descends from top-most visible ancestors as one
    downward tree (ancestors top, focus middle, descendants bottom).
  - Recursive measure/place packs subtrees left→right and centers each parent-unit over its children.
  - Connectors are now clean axis-aligned segments per family: stem down from couple midpoint →
    horizontal bus spanning only that family's children → vertical drop to each child. Spouse/divorce
    = short horizontal segment between the adjacent couple. Non-primary parent = individual elbow.
  - COL_W 128, ROW_H 168. All edges rendered as react-native-svg <Line> (removed diagonal/Path).
- export-pdf unaffected (still consumes buildLayout nodes/edges); caption reworded.
- Verified via seeded 3-gen family screenshot: couple links short, children hang from localized bus,
  no cross-generation spiderweb.

## Iteration 8c — Standard family-tree behaviour (hide in-law extended families) (2026-06)
- User feedback ("masih ngaco, tiru aplikasi serupa"): the long cross-generation lines came from the
  canvas pulling in an in-law's whole family (spouse's parents + siblings) and drawing long
  secondary-parent / sibling lines across the row.
- Fix in src/tree-layout.ts (matches how standard family-tree apps render the main chart):
  - BFS now only EXPANDS blood relatives (parents/children/siblings). A spouse is placed INLINE at the
    same generation but is NOT expanded, so an in-law's own ancestors/siblings never appear on the main
    canvas (still visible via Explorer / person detail). Removes the tangle at the source.
  - Co-parents (two people sharing a visible child) are merged into a couple unit even without an
    explicit spouse relation, so both parents sit together above their children.
  - Explicit sibling relations render as a small bracket ABOVE the two nodes (up→across), never a raw
    line through the row.
- index.tsx: initial view now FITS the whole tree to screen width and centres it (center-origin scale
  math), so the clean structure is visible at a glance; pinch-zoom/pan still work. Refits on focus/filter change.
- Verified against the user's real tree (temp read session, then removed): renders as a clean org-chart —
  Iqbal+Deliana → Erick(+Mahdiana)/Antony/Veronica → grandchildren; in-laws hidden.

## Iteration 8d — Revert tree layout to ORIGINAL scheme (per user request) (2026-06)
- User asked to restore the tree diagram model to the ORIGINAL (as built when siblings kakak/adik were
  added), WITHOUT removing any current features.
- Reverted src/tree-layout.ts to the original flat generational layout: BFS in all directions (shows
  in-laws & their families again), each generation centered in its own row, spouses reordered adjacent,
  straight-line edges (parent diagonal, spouse/sibling horizontal). Removed the tidy/org-chart engine,
  couple-merge, in-law hiding, and sibling brackets.
- KEPT all newer features: DD/MM/YYYY DateField, marriage/divorce edit modal + PUT /relations,
  add-relative child auto-link to single spouse, "Jadikan Pusat Pohon", filter panel copy, export from
  current filtered view, and the fit-to-screen initial camera (so the whole original tree is visible).
- Verified on the user's real tree via temp read session (removed after): all 16 members / 3 gens render
  in the original scheme with straight connectors.




## Iteration 9 — "Sembunyikan Saudara" (direct-line only) toggle (2026-06)
- Filter panel (tree tab) gained a toggle "Sembunyikan Saudara (Kakak/Adik)" (testID toggle-hide-siblings).
- When ON, the canvas shows ONLY the direct line relative to the current center (activeFocus): the focus
  + spouse(s), direct ancestors up `filterUp` gens, direct descendants down `filterDown` gens. Siblings,
  aunts/uncles, cousins and in-law extended families are excluded. Implemented via `directLineSet()` in
  app/(tabs)/index.tsx that filters people/relations before buildLayout (sibling relations dropped too).
- POV-consistent by design: because the set is keyed on activeFocus, making any person the tree center
  (via "Jadikan Pusat Pohon" or the crosshair focus button) recomputes the direct line from THAT person's
  point of view. Verified on real data: focus=Erick → Erick+Mahdiana+parents+children; focus=child(Ahmad)
  → Ahmad + Erick + Iqbal/Deliana (2 gens up), siblings hidden.
- i18n keys hide_siblings / hide_siblings_desc (ID+EN). State is per-session (not persisted).

## Iteration 9b — Link children to BOTH parents (fix one-parent children) (2026-06)
- Root problem: existing children were linked to only one parent (father), so from the mother's POV
  (and downward generations generally) they looked disconnected / tempted the user to create a duplicate
  mother.
- Backend: NEW POST /api/tree/link-coparents (admin/editor). For the whole tree, links each child to the
  OTHER parent (the linked parent's spouse) when unambiguous: child has exactly ONE parent AND that parent
  has exactly ONE spouse. Reuses the existing spouse — never creates a new person. Returns {linked}.
- Frontend: Settings → tree section → "Hubungkan Anak ke Kedua Orang Tua" (testID repair-parents-row)
  calls it and alerts how many were linked. api.ts linkCoparents(). i18n repair_parents* (ID+EN).
- directLineSet (hide-siblings) also seeds descendants from the focus COUPLE so shared children show from
  either partner's POV even before repair.
- Ran the repair on the user's real tree via temp session: linked 5 children to Mahdiana (Erick's wife);
  verified both Erick & Mahdiana now connect to the 5 kids. Data fixed; POV now consistent for everyone.
- Future children already auto-link to both parents via the earlier add-relative fix (single-spouse case).

## Iteration 9c — Multiple-spouse: choose the child's other parent (2026-06)
- User request: support a person with >1 spouse — when adding a child, pick which spouse is the child's
  other parent (e.g., child A belongs to Erick's 2nd wife). Apply to every individual.
- Backend: AddRelativeInput gained optional `other_parent_id`. In the child branch, the other parent is:
  (a) the explicit other_parent_id if it is a valid spouse of the focus, else (b) auto-link when the focus
  has exactly one spouse, else (c) none. Verified 4 cases via localhost API test (explicit w1/w2 link both
  parents; ambiguous/invalid safely link only the focus).
- Frontend add-relative.tsx: for direction=child, loads the focus's spouses; when there are ≥2 spouses it
  shows a chip picker "Anak ini dari pasangan yang mana?" (testIDs other-parent-<id>, other-parent-none)
  and passes other_parent_id. A 2nd+ spouse can be added via the always-additive +Pasangan / add-spouse
  buttons. i18n choose_other_parent / unknown_parent (ID+EN).

## Iteration 9d — Direct-line is now the DEFAULT view + "Lihat Semua" (2026-06)
- Per user: default tree view = direct line (hide siblings) for EVERY person; removed the hide-siblings
  checkbox; added a "Lihat Semua" (View All) button.
- index.tsx: hideSiblings now defaults to TRUE. Filter panel: removed the toggle, added a hint line, and
  the two footer buttons are now "Lihat Semua" (testID filter-view-all → hideSiblings=false + gens 99/99,
  shows the whole family/all generations) and "Terapkan" (testID filter-apply → hideSiblings=true, applies
  the ancestor/descendant stepper depth). i18n view_all / direct_line_hint (ID+EN).
- POV-consistent: because directLineSet is keyed on activeFocus and hideSiblings defaults true, making
  anyone the tree center shows, by default, that person + spouse + N gens up/down (default 2/2).
- Verified on real tree: default shows Erick+Mahdiana+parents+5 children (siblings/in-laws hidden); filter
  panel shows the new buttons and hint.




