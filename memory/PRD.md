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





## Iteration 10 — Onboarding + Join Tree flows + Tree Switcher (2026-06)
- FLOW 1 (Onboarding): app/welcome.tsx — new users (0 trees) land here. Two cards: Buat Pohon Baru
  (name sheet -> createTree -> setActive -> tabs) and Gabung Pohon yang Ada (-> /join). RootNav (_layout.tsx)
  redirects authed users with trees.length===0 to /welcome (welcome/join/invite exempt). Backend no longer
  auto-creates a tree per new Google user (they choose in onboarding).
- FLOW 2 (Join Tree): app/join.tsx — 3 tabs: Link/Kode (paste link/code -> acceptInviteLink), Cari
  (searchTrees public trees -> requestJoin -> pending chip), Scan QR (expo-camera qr, permission per contract,
  parses /invite/{token} or tree_* id). CAMERA ONLY WORKS ON NATIVE BUILD (not Expo Go/preview).
- Tree Switcher: index.tsx header title tappable (chevron-down) -> /trees modal. trees.tsx gained Gabung Pohon btn.
- members.tsx admin: Pohon Publik Switch (setTreeVisibility) + Permintaan Gabung approve/reject (actJoinRequest).
- app.json: NSCameraUsageDescription (iOS), CAMERA (Android), expo-camera plugin.
- Backend verified by testing_agent: 27/27 PASS. i18n keys welcome_*/join_*/tab_*/camera_* (ID+EN) added.
- PENDING next: Tahap 5 tree limit enforcement UI (Free=50 upgrade modal + CLAIM CABANG forces free plan).

## Iteration 11 — Node grow animation + Limit gate + Klaim Cabang (2026-06)
- ANIMASI NODE: index.tsx GrowNode now animates ONLY newly-added nodes (tracked via animRef ctxKey =
  tree|focus|hideSiblings|up|down). New node grows/translates FROM its parent node position (originFor()
  finds parent/neighbor that is already positioned). Existing nodes stay static; no mass-animation on load,
  tree switch, or filter toggle.
- BATAS POHON: add-relative.tsx onSubmit now catches 402/LIMIT_REACHED -> UpgradeModal (covers canvas,
  person-detail quick-add, and Add tab since all route through add-relative). index openAdd keeps its
  pre-check. Verified backend still returns 402 LIMIT_REACHED at 50 people (Free).
- KLAIM CABANG: NEW POST /api/trees/{tid}/claim-branch (any member). Copies a person into a NEW free tree
  owned by caller; source untouched. scope=descendants|children|whole; includes spouses of selected; relations
  remapped (both endpoints in set). Claimed person = is_root of new tree. api.ts claimBranch(). New screen
  app/claim-branch.tsx (person picker + 3-option scope radio + optional name). Entry points: person detail
  Klaim Cabang button + Profil/Setting row (all members). Backend verified 12/12 PASS.
- i18n keys claim_*/scope_* (ID+EN). Frontend behind Google OAuth = user manual test.

## Iteration 12 — WhatsApp-style multi-room Chat + double-tap POV (2026-06)
- CHAT REDESIGN: single family group -> multi-conversation. New collection chat_rooms {id,tree_id,type
  (family|group|direct),name,member_ids,dm_key?,created_by,created_at}. Family room is virtual (id==tree_id)
  so existing family_chat messages (room_id==tree_id) keep working. Messages stay in family_chat with room_id.
  - Endpoints: GET /chat/rooms (list convos: family pinned + groups/DMs, last msg + unread), GET /chat/contacts,
    POST /chat/group (admin/editor only), POST /chat/direct (idempotent via dm_key). get_chat & send_chat & typing
    now take ?room_id=. Helpers resolve_room / is_user_deceased / notify_room.
  - RULES (user): DM+groups; only admin/editor create groups; NO alive filter -> a member whose linked person
    (by email) is deceased CANNOT send (403). Removed the old alive-only toggle UI entirely.
  - Frontend: app/(tabs)/chat.tsx = WhatsApp conversation LIST (avatar, last msg, time, unread badge, New Chat).
    app/chat/[roomId].tsx = conversation screen (room-scoped, mentions only for non-direct). app/chat/new.tsx =
    contacts list (tap -> DM) + Buat Grup (name + multi-select, admin/editor). Routes registered in _layout.
  - Backend verified by testing_agent: 26/26 PASS. Fixed delete_chat to resolve by tree_id (group/DM delete).
- CANVAS: double-tap a node -> jump into that person direct-line POV (setFocusId + hideSiblings=true).
  Single tap still selects (add buttons); deliberate 2nd tap (>320ms) still opens detail. Nothing removed.

## Iteration 13 — Delete tree + Manage group + Mute chat + auth note (2026-06)
- DELETE /trees/{tid} owner-only, cascades 12 collections. Frontend trees.tsx: trash icon on OWNED tree rows
  (owner_id==user) -> confirm Alert -> deleteTree; if active deleted, switch to first remaining or /welcome.
- PUT /chat/rooms/{room_id} (group rename + replace members; creator/admin/editor only). Frontend
  app/chat/manage/[roomId].tsx (name input + contacts checkboxes). Reached via chat settings sheet -> Kelola Grup.
- POST /chat/rooms/{room_id}/mute + chat_mutes collection. notify_room skips muted users. list_chat_rooms &
  get_chat return muted flag + can_manage. Frontend: settings sheet (more-vertical) in [roomId] with Mute Switch;
  chat list shows bell-off icon when muted. Backend verified 16/16 PASS.
- AUTH: Invalid state parameter on logout->login is PROVIDER-SIDE (auth.emergentagent.com validating its own
  OAuth transaction cookie). integration_expert + support confirmed not reliably fixable in app JS. Earlier fix
  (window.location.replace for outbound auth) kept. User advised to clear auth.emergentagent.com cookies / test
  deployed build, and contact support@emergent.sh if it persists.

## Iteration 14 — PDF fix + Cetak Buku + Midtrans (production) + delete-tree fix (2026-06)
- PDF EXPORT BUG: on web, expo-print printed the current page (export modal). Fixed: export-pdf.ts now
  opens the generated tree HTML in its own window on web (outputPdf helper); SVG given explicit width/height.
- CETAK BUKU SILSILAH (paket family): exportTreeBook() -> cover + full-tree page + one profile page per member
  (photo/initials, JK, lahir, tempat, pekerjaan, wafat, catatan). Button in export modal on index.tsx, gated to
  plan===family. Shared buildTreeSvg/outputPdf helpers.
- MIDTRANS (PRODUCTION): backend /payments/snap (admin, per active tree), /payments/notification (sha512 sig
  verify -> activate tree.plan), /payments/status/{order_id} (owner poll + proactive Midtrans status check).
  payment_orders collection. Keys in backend/.env (MIDTRANS_*). Prices pro=149000, family=199000. Frontend
  subscription.tsx: real flow via createSnap -> open redirect_url (web window.open / native WebBrowser) -> poll
  status -> refreshTrees. Backend verified 14/14 PASS.
  ACTION: user must set Payment Notification URL in Midtrans dashboard to <backendUrl>/api/payments/notification
  (update after deploy). Production keys = real charges; user advised to rotate exposed server key.
- DELETE TREE FIX: Alert.alert confirm does not work on RN-Web (no response). Replaced with a custom Modal
  confirm in trees.tsx (Batal/Hapus). Owner-only trash icon.

## Iteration 15 — Admin Dashboard verify + Payment History + Premium Themes + DATA-LOSS incident (2026-06, fork)
- SUPERADMIN DASHBOARD: verified complete (was already wired). Backend /admin/overview, /admin/users,
  /admin/feedback (email gate via SUPERADMIN_EMAILS=emmusic.indonesia@gmail.com). Link in settings.tsx shown
  only when user.is_superadmin. admin.tsx UI = Ringkasan/User/Masukan tabs. Backend tested 12/12 PASS.
- PAYMENT HISTORY (Riwayat Pembayaran): backend GET /payments/history returns current user's payment_orders
  (desc, enriched with tree_name). Frontend app/payment-history.tsx (status chips paid/pending/failed) + link
  row in subscription.tsx. Self-tested 200 + correct shape.
- PREMIUM THEMES (Tema Premium): theme.ts refactored -> ThemeProvider context + usePremiumTheme + useTheme now
  returns dynamic `gradient`. 5 palettes: heritage(free default), emerald/rose/midnight/terracotta(PRO). Persisted
  in storage key "premium_theme". Picker at app/themes.tsx (gated: premium themes route free users to
  /subscription). Link in settings Preferences. All brandGradient consumers (GradientButton, UpgradeModal,
  subscription, welcome, claim-branch, invite) switched to useTheme().gradient. brandGradient export kept as
  default (heritage) for back-compat.
- *** DATA-LOSS INCIDENT + PREVENTION ***: Running testing_agent for admin dashboard executed
  test_admin_dashboard.py whose fixture did db[name].delete_many({}) on ALL collections (users/trees/people/...)
  at setup AND teardown -> wiped real user data (tree_e21f7335f5c1 etc.). No oplog/backup existed.
  FIX: rewrote test_admin_dashboard.py fixture to seed + delete ONLY its own synthetic docs (tracked ids/uids/
  tokens); removed all delete_many({}) whole-collection wipes. Added safety net: /app/scripts/db_backup.sh does
  hourly mongodump (gzip) to /app/backups (persistent PVC), keeps last 24; registered in root crontab
  (0 * * * *); baseline snapshot taken. RULE for future: NEVER allow testing_agent/tests to run delete_many({})
  on shared collections; always scope deletes to synthetic docs.

## Iteration 15b — FIX: foto data diri gagal (upload & kamera) (2026-06, fork)
- ROOT CAUSE: POST /upload used deprecated GLOBAL require_role(user,["admin","editor"]) but multitenant roles
  live in tree_members. New Google users get GLOBAL users.role="viewer" (e.g. emmusic) -> every photo upload
  returned 403 for them, so photo never appeared (frontend swallowed the error silently).
- FIX (backend): /upload now takes tree_id query + resolve_tree(user,tree_id) + require_role_t(role,["admin",
  "editor"]) — same per-tree pattern as /people/{id}/files.
- FIX (frontend): uploadPhoto() appends ?tree_id=<activeTreeId> and now throws the server detail; PersonForm
  shows uploadErr text under the photo buttons instead of failing silently.
- Verified e2e: user with GLOBAL role=viewer but tree role=admin -> upload 200 + /files fetch 200 (image/png).

## Iteration 16 — Foto: kompres, ganti/hapus, Galeri Anggota + superadmin full access (2026-06, fork)
- SUPERADMIN FULL ACCESS: resolve_tree() now returns role="admin" for any superadmin (email in
  SUPERADMIN_EMAILS) on any tree they belong to, and grants access even to trees they aren't a member of.
  Permanent full access via env email (emmusic.indonesia@gmail.com).
- KOMPRES FOTO: added expo-image-manipulator + src/utils/image.ts compressImage(uri,maxDim=1080,compress=0.6)
  -> resize+JPEG. Used in PersonForm.doUpload and person gallery add. Falls back to original on error.
- GANTI/HAPUS FOTO: PersonForm now shows remove (X) badge on avatar + "Ganti Foto"/"Hapus Foto" buttons when
  a photo exists. Removing sets photo_url=null.
- GALERI ANGGOTA (memory gallery): person.gallery = string[] of storage paths.
  Backend: POST/DELETE /people/{id}/gallery {path} ($push/$pull), gated admin/editor, plan photos limit uses
  photo_count+gallery_count. get_person returns gallery. Frontend: horizontal gallery in person detail "Data"
  tab with add (pick->compress->upload->addGalleryPhoto) + per-photo delete + tap to view in existing viewer.
  Verified backend e2e (add x2 / get / delete). api: addGalleryPhoto, removeGalleryPhoto; Person.gallery.
- Animation grow node: confirmed already implemented (GrowNode + originFor grows new node from parent). Offered
  to make more pronounced; user moved on to photo features.

## Iteration 16b — FIX: ekspor PDF berantakan / tumpah banyak halaman (2026-06, fork)
- ROOT CAUSE: buildTreeSvg emitted SVG with fixed dispW=760 + dispH scaled by aspect ratio -> tall/narrow trees
  produced a very tall SVG that overflowed across pages (blank page 1, nodes split across pages 3-4). No @page
  size/margins so nothing fit A4.
- FIX (export-pdf.ts): SVG now responsive `<svg class="treesvg" viewBox=... preserveAspectRatio="xMidYMid meet">`
  (no fixed px). exportTreePdf + exportTreeBook CSS now set @page{size:A4 portrait;margin:14mm},
  .treesvg{width:100%;height:150mm}(book 210mm), page-break-inside:avoid on tree/rows/datasec/profile, removed
  unreliable min-height:92vh (book), added <meta charset=utf-8>. Watermark moved into 6mm/8mm safe area.
- Verified: rendered representative HTML at A4 (794x1123) print media -> title + full tree (all nodes visible,
  none cropped) + full Data Anggota table all fit within ONE A4 page (scrollHeight==1123).

## Iteration 16c — FIX: dashboard superadmin tidak muncul setelah login (2026-06, fork)
- ROOT CAUSE: auth.tsx exchange() set user from authSession() response (raw db user, NO is_superadmin).
  Only getMe()/refresh() include is_superadmin. So after a fresh login the settings "Admin Dashboard" row
  (gated on user?.is_superadmin) stayed hidden until app reopen.
- FIX: exchange() now calls getMe() after storing token and sets that (fallback to res.user on error).
- Verified backend /auth/me returns is_superadmin=true for emmusic.indonesia@gmail.com.

## Iteration 17 — FIX: deployment health check + regression (2026-06, fork)
- DEPLOY BLOCKER: K8s health probe hits GET /health (root, no /api prefix) -> 404 (all routes under /api).
  FIX: added root-level @app.get("/health") -> {"status":"ok"} in server.py (right after app/api_router init).
  Verified 200 locally. The repeated 404 logs in the deploy report were stale (pre-fix).
- REGRESSION FIX: while inserting /payments/history earlier, the @api_router.get("/trees/{tid}/members")
  decorator was accidentally deleted, unregistering the Manage Members GET route (would 404 on client).
  Caught by deployment_agent. Restored decorator; now returns 401 unauth (registered). 
- NOTE (not blockers): hardcoded Emergent auth URL demobackend.emergentagent.com/auth/v1/env/oauth/session-data
  is the standard Emergent-managed Google Auth endpoint (same across envs) — left as-is per playbook.
  Google Drive backup row is an intentional "coming soon" placeholder gated to Pro.

## Iteration 18 — FIX: "Unsupported FormDataPart implementation" upload/capture foto di device (2026-06, fork)
- ROOT CAUSE: Expo SDK 54 (expo 57.0.19) global fetch is the "winter" fetch, which rejects the legacy RN
  FormData part { uri, name, type }. So on real devices every photo upload threw "Unsupported FormDataPart
  implementation" (worked on web via Blob).
- FIX (src/api.ts uploadPhoto): native branch now appends `new FsFile(uri)` (File from "expo-file-system",
  which `implements Blob`) instead of { uri,name,type }. Web branch unchanged (Blob). Verified File is exported
  and constructor accepts a file:// uri string in expo-file-system@57.0.6.
- NATIVE-ONLY: can't be validated on web preview; test on Android/iOS via Expo Go. Web bundling confirmed OK.

## Iteration 19 — Kanvas warna garis + animasi, Kartu Anggota (cover+galeri IG+caption), foto profil chat (2026-06)
User choices: chat avatar = account photo (changeable) [1b]; order Fase 1->2->3 [2a].
FASE 1 (kanvas):
- tree-layout.ts: added LINEAGE_COLORS[10] + lineageColor(); compute per-branch lineage index (root couple=branch0,
  each child of a top ancestor = new branch, descendants inherit, married-in spouses inherit partner). LayoutNode.lineage
  + LayoutEdge.lineage (child's). index.tsx: parent-child lines colored by lineage (width 3.5), PersonNode ring=lineageColor
  + small gender dot. GrowNode animation stronger (travel from parent 620ms + spring pop overshoot).
FASE 2 (kartu anggota person/[id].tsx):
- Backend: PersonData +cover_url; gallery items now objects {id,path,caption,date,created_at} (was string[]).
  Endpoints: POST gallery {path,caption,date}, PATCH /gallery/{photo_id} {caption,date}, DELETE by {id}. get_person
  returns serialized gallery. api.ts GalleryPhoto type + addGalleryPhoto(caption,date)/editGalleryPhoto/removeGalleryPhoto(id).
- UI: Facebook-style cover header (150px) with change button (editor), avatar overlaps cover (marginTop -60),
  tighter InfoRow (paddingVertical 9), Instagram-style gallery (square img + caption + date + edit/delete),
  caption editor modal (caption + free-text date). Person.cover_url + gallery:GalleryPhoto[].
FASE 3 (chat avatar = account photo, changeable):
- Backend PUT /users/me {name?,picture?}. api.ts updateProfile. settings.tsx profile avatar now tappable ->
  pick+compress(512)+upload+updateProfile+refresh, camera badge overlay, uses fileUrl(user.picture).
  chat/[roomId].tsx sender avatar now fileUrl(sender_picture) so uploaded (relative) avatars resolve.
- Verified backend e2e (gallery add/edit/delete caption+date, cover set, profile pic). Auth-gated UI needs device test.

## Iteration 20 — FIX: grup chat tersembunyi, restore picker, klarifikasi "data hilang" (2026-06)
- GRUP CHAT tersembunyi: chat/new.tsx canGroup dulu pakai GLOBAL user.role (viewer utk emmusic) -> tombol
  "Grup Baru" tidak muncul. FIX: pakai activeTree.role (fallback user.role) + is_superadmin. Entry: tab Chat ->
  tombol pensil (new-chat-button) -> /chat/new -> "Grup Baru".
- RESTORE picker: DocumentPicker type "application/json" sering menampilkan galeri & file .json tak bisa dipilih
  di Android. FIX: type ["application/json","text/plain","*/*"].
- DATA "hilang lagi": DIVERIFIKASI via mongorestore backup 08:00 == kondisi sekarang (4 people, 2 trees, 3 rel).
  Tidak ada kehilangan sejak backup pertama. Ada DUA akun/pohon bernama sama "Erick De Vries":
  limajiwamandiri (1 person) & emmusic (3 person: Erick Devries, Siti Annisa, Mahdiana). Kemungkinan user
  bingung antar akun. Kehilangan sebelumnya (pra-backup 07:33) tak terpulihkan. Backup baru dibuat.

## Iteration 21 — Seed empty tree + create new tree flow (2026-06)
- PROBLEM: empty tree canvas had no way to add the FIRST person (Add tab needs an existing target; canvas empty
  state was text-only). User couldn't start a new/empty tree.
- Backend: POST /people/first {PersonData} -> creates root person if tree has 0 people (else 400), sets
  trees.root_person_id. require_role_t admin/editor. FIX: return _serialize([doc])[0] (was passing dict).
- Frontend: new modal route app/add-first.tsx (PersonForm -> addFirstPerson). Empty canvas state (index.tsx)
  now shows "Tambah Orang Pertama" button (canEdit). Add tab (add.tsx) shows seed screen when people.length===0.
  api.ts addFirstPerson. i18n first_person_title/sub. Route registered in _layout.
- Create NEW tree: already works via header tree-switcher -> /trees -> create (dashed) button; createTree
  auto-makes a root person + sets active. Verified seed endpoint e2e (first ok, second 400, root set).

## Iteration 22 — FIX: birthday stat card text terpotong di HP (2026-06)
- stat-birthday card: value now "H-<days>" (🎂 on day), label "<name> ultah" / "<name> ultah hari ini!".
  statValue adjustsFontSizeToFit; statLabel numberOfLines=2 + adjustsFontSizeToFit minimumFontScale 0.8 so
  full text fits inside the card. i18n birthday_short/birthday_today_short (ID+EN).
- VERIFIED by testing_agent (iteration_12.json): renders "H-56" + "Mahdiana ultah", fits at 360px & 390px,
  fallbacks ok, real data untouched. Safe seed script: backend/tests/seed_stat_birthday.py (scoped cleanup).

## Iteration 23 — Notif chat (badge dalam aplikasi) [user chose 1b] (2026-06)
- FINDING: in-app chat unread badge ALREADY fully implemented & working. No Firebase/push needed.
  - send_chat -> notify_room() inserts app_notifications type "chat" for all family/room members except
    sender & muted.
  - Tab bar badge: (tabs)/_layout.tsx reads /notifications unread_chat (poll 8s) -> red number on Chat icon.
  - Per-room unread badge in chat list (chat.tsx, from /chat/rooms read_by count).
  - Cleared via markNotificationsRead("chat") on opening chat list & room.
  - VERIFIED e2e (scoped test): A sends -> B unread_chat=1 -> after read=0 -> sender stays 0. Real data untouched.
- No code change this turn. Possible future: dedicated notifications inbox (bell) screen (items already returned).

## Iteration 24 — Chat photo fix + Notif Inbox + Push + WA-style group/mention + test safety (2026-06, fork)
User choices: chat notif = getar + suara "ding"; kerjakan Push sekarang.
- CHAT PHOTO FIX: chat/[roomId].tsx sendPhoto now compressImage() before uploadPhoto (raw content:// URIs
  failed the winter-fetch File ctor; profile/gallery already compressed → worked). Errors now surfaced via Alert.
- NOTIF INBOX: notifications.tsx wired (was orphaned) — added AppNotification type + typed getNotifications in
  api.ts, i18n no_notifications (ID/EN), route registered in _layout, bell icon + unread badge in Tree header
  (index.tsx) → /notifications. markNotificationsRead on blur.
- CHAT HAPTICS + DING: expo-audio + expo-haptics. chat/[roomId].tsx plays assets/ding.wav + Haptics on NEW
  incoming message (not mine, not muted). Generated ding.wav (sine ding) in assets/.
- PUSH (Emergent relay): backend send_push() + POST /register-push (auth, derives user_id) + notify_room fans
  out push (channel_id chat, sound ding.wav, action_url /chat/{room}) wrapped try/except (non-blocking).
  EMERGENT_PUSH_KEY=placeholder in backend/.env. Frontend _layout.tsx: module-scope setNotificationHandler +
  Android channels (default + chat w/ ding), tap handlers (warm+cold), device registration after auth,
  weekly denied nudge → Linking.openSettings. app.json: expo-notifications plugin sounds:[ding.wav] +
  android.googleServicesFile ./google-services.json. NEEDS user google-services.json + native build to test.
- WA-STYLE GROUP: chat/new.tsx added contact search + selected-member chips (avatar + remove). i18n search_contacts.
- WA-STYLE MENTION: chat/[roomId].tsx inline @autocomplete overlay above input (typing @ filters members,
  tap inserts @Name) replacing the old modal picker. @ button now inserts "@" trigger.
- TEST SAFETY: conftest.py `seeded` fixture now SKIPS (refuses) when DB has non-TEST_ users so its whole-collection
  delete_many({}) can never wipe real data again.
- Backend verified by testing_agent 9/9 PASS (upload, chat attachments, register-push 401/500, notifications,
  read, non-blocking push, mention notif). Real trees untouched. Frontend UI (behind Google OAuth) = user device test.

## Iteration 25 — Foto Grup + Swipe-to-reply + Nada Notif Chat (2026-06, fork)
- FOTO GRUP: chat_rooms.picture. Backend GroupCreateInput/GroupUpdateInput +picture; create_group & update_group
  persist it; get_chat returns room_picture (+members now include picture). api.ts createGroup/updateGroup take
  picture. chat/new.tsx group mode shows circular photo picker (pick→compress512→uploadPhoto). chat/manage shows
  editable group photo (88px + edit badge). chat list & room header already render picture.
- SWIPE-TO-REPLY: chat/[roomId].tsx module-scope SwipeableMessage (gesture-handler Pan + reanimated). Drag a
  message right >56px → Haptics medium + setReplyTo (WhatsApp-style), snaps back; reply arrow fades in on left.
  Enabled only when canChat. activeOffsetX(16)/failOffsetY so vertical scroll unaffected.
- NADA NOTIF CHAT: generated assets chime/pop/bell.wav (+ding). src/utils/chat-sounds.ts registry (ding/chime/
  pop/bell/none) persisted key "chat_sound". New screen app/chat-sound.tsx (list + play preview + radio select,
  expo-audio). Settings→Preferences row "Nada Notifikasi Chat". chat/[roomId].tsx loads chosen sound (soundRef +
  dingPlayer.replace) and skips play when "none"/muted. Route registered. i18n chat_sound/chat_sound_hint (ID/EN).
- Backend group-photo verified e2e (create+get+update picture, members carry picture). Frontend behind OAuth = device test.

## Iteration 26 — Info Grup + Status Dibaca Grup (2026-06, fork)
- INFO GRUP: get_chat members now include role (from tree_members) + is_creator; response adds created_by.
  New screen app/chat/info/[roomId].tsx (WhatsApp-style): big group photo + name + member count, actions
  (Bisukan switch, Kelola Grup if can_manage, Keluar Grup if group), member list with avatar + badge
  (Pembuat grup / Admin / Editor). Entry: tapping the chat room header (name/photo) for non-direct rooms.
  Route registered.
- STATUS DIBACA GRUP (read receipts): message action sheet (long-press own message in group/family) gained
  "Info Pesan" → modal listing "Dibaca oleh" (readers, from message.read_by mapped to members) and
  "Belum dibaca" (pending) with avatars. No backend change (read_by already tracked; members now carry picture).
- i18n group_info/group_members/group_creator/badge_admin/badge_editor/read_by/delivered_to/message_info (ID/EN).
- Backend verified: get_chat returns members[role,is_creator] + created_by. Frontend behind OAuth = device test.
