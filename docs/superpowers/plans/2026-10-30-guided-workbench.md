# Guided Campus Workbench Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. User authorized implementation in the current shared project.

**Goal:** Deliver guided dataset workflows and a coordinated square-corner campus interface across all active pages.

**Architecture:** Reuse Vue3/Element Plus/ECharts and existing dataset/training/delivery APIs. Shared CSS, SVG icons and school branding establish the shell; view tabs and a persisted dataset purpose provide task navigation without deleting existing evidence.

**Tech Stack:** Existing Vue3, TypeScript5.9.3, Java21/Spring, MySQL. No new packages.

**Spec:** docs/superpowers/specs/2026-10-30-guided-workbench-design.md

## Global Constraints
- User-provided PNGs copied byte-for-byte. Straight corners, no chart export, concise copy.
- Keep ADMIN/REVIEWER data/training permissions, MEMBER writing; unchanged model weights and paused formal generation.
- Source baseline: runtime/source-checkpoints/frontend-before-20261030. Existing local Git has no usable tracked baseline; continue checkpoint + GitHub connector on codex branch, do not reset Git metadata.

## Review Focus
- New visitors and empty datasets: usable next action, no misleading completion.
- Persisted use purpose and PAIRS validation: no reference import from sentence pairs.
- Model training version versus latest dataset version: recover original identity and intentional alternatives.
- Long running work and navigation: tasks persist, no duplicate execution on rendering, no loss of manuscript.
- Short/narrow viewports and dark mode: controls visible, keyboard operable, school wordmark legible.

### Task 1: Campus shell and design system
Files: public/brand/*.png, components/AppIcon.vue, layouts/AppLayout.vue, style.css, styles/workbench.css, views/LoginView.vue, views/HomeView.vue.
- [x] Preserve baseline; copy supplied assets; shared icons, tokens, fixed shell and responsive navigation.
- [x] Update role home and login, semantic button/link appearance and short guidance.
- [x] Build and visually inspect login and shell. No tests for CSS-only appearance changes.

### Task 2: Guided data preparation and purpose
Files: views/DatasetView.vue, api/workbench.ts, workbench/DatasetService.java, DatasetController.java, migration009, shared workflow component/helper.
- [x] Add persisted purpose with NEWS/PAIRS validation, preserve existing API callers.
- [x] Add focused purpose validation check, watch failure then pass for logic.
- [x] Move import to deliberate action, add actual-state process steps, carry dataset/version into training and reference import.

### Task 3: Training and model workspace
Files: TrainingView.vue, ModelView.vue, AutomaticPipeline.vue, training/workbench shared helpers.
- [x] Separate new training / tasks / school progress; place creation at top and show only relevant algorithm fields.
- [x] Model details tabs, readable parameters, metrics help, preserve results and task history.
- [x] Focused check: restore model inputVersionId and preparationId rather than latest; wrong/missing versions explain recovery.

### Task 4: Remaining role and delivery views
Files: ReleaseView, ReferenceImportView, reference/list/editor, manuscript/history/review, publications/source, SystemView and evidence components.
- [x] Separate operation form/result/history; prominent current state and actions; coherent styles and role navigation.
- [x] Keep shared draft and strict citation evidence; add summaries, readable stage labels and keyboard alternatives.

### Task 5: Deploy and verify
- [x] Relevant frontend checks, production frontend + backend build with existing offline environment.
- [x] Verify idle Java then restart only owned Java; detector/OCR/models unchanged; ensure no generation resumed.
- [x] Actual browser layout and API checks, one final read-only review with focused fixes.
- [x] Update current progress/ledger, source checkpoint, GitHub non-force CAS update + readback. Report completed scope and remaining work accurately.

### Task 6: Universal custom record pagination (user-added)
Files: components/RecordPagination.vue, all active record views/API wrappers, backend existing paged controllers/services; new full-history endpoints.
- [x] Add numeric custom size1–100 + page jumper; retain filters and reset to1 on size change.
- [x] Backend limits/long offsets with validation; preserve defaults/role restrictions and old overloads.
- [x] Complete history endpoints for dataset tasks, release changes, manuscript/submission checks, preserve old summary arrays.
- [x] Focused widget behavior +3 backend pagination/access checks pass.
- [x] Deployed custom size and page jump verified against actual API/UI.
