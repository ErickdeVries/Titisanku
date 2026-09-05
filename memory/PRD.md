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

## Backlog / Next
- P1: Marriage/divorce dates shown on spouse relation in detail view.
- P1: Reposition/refocus tree on any selected person (currently rooted at root_node).
- P2: Node de-overlap layout for very wide generations.
- P2: Import from JSON backup (restore).
- P2: Offline caching of tree.

## Notes
- Birthday reminders + image picker require a native/dev build to fully test (not Expo Go web).
