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
