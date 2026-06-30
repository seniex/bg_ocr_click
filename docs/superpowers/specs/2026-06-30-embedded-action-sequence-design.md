# Embedded Action Sequence And Compact Group Editor Design

## Objective

Update the Qt monitor group editor so users can edit action sequences directly inside the group
module instead of editing visible raw JSON by default. At the same time, make the monitor group
editor more compact by grouping related controls and hiding popup-flow controls unless popup flow is
enabled.

Business behavior and saved configuration schema should remain compatible with the existing runtime.

## Confirmed Requirements

- The action sequence JSON area is hidden by default.
- A JSON button opens a separate raw JSON editor window when direct JSON editing is needed.
- The group editor directly shows action sequence controls.
- Action buttons add typed actions directly: mouse, key, delay, scroll, and text.
- Each action row shows only fields relevant to that action type.
- Action rows can be selected and moved to any position through row movement controls and drag/drop
  ordering.
- Mouse actions show only: pre-delay seconds, position mode, offset X/Y, click method, click count,
  and interval seconds.
- Delay actions show only: wait seconds.
- Key, scroll, and text actions follow the same typed-row rule and expose only their own fields.
- Group editor controls are tightened into related sections instead of placing every editable field on
  a separate full-width row.
- Popup-flow controls are fully hidden when "enable popup flow" is unchecked. Only the enable checkbox
  remains visible.
- Every editable combo box and spin box must ignore mouse-wheel changes unless it has focus.

## Recommended Approach

Implement a reusable Qt action sequence editor widget inside `bg_ocr_qt_actions.py`, then embed it in
`_GroupEditor`.

This keeps action sequence behavior near the existing action dialog code, avoids changing runtime
action execution, and gives tests a focused surface for typed rows, JSON roundtrip, reordering, and
wheel handling.

## Components

### Action Sequence Widget

Add an embedded widget that owns:

- An action toolbar with buttons for mouse, key, delay, scroll, text, and JSON.
- A reorderable action list or row container.
- One row editor per action.
- Conversion between widget state and the existing `actions` list of dictionaries.

The widget should preserve unknown action kinds and unknown fields when possible. Unknown actions can
be shown as a compact raw/summary row and still roundtrip through save.

### Raw JSON Editor

Keep raw JSON editing available but opt-in:

- The JSON button opens a small dialog containing a `QPlainTextEdit`.
- Accepting valid JSON replaces the embedded action list.
- Invalid JSON should not silently destroy the existing action list; it should either reject with a
  message or keep the previous value.

### Compact Group Editor Layout

Replace the single long `QFormLayout` usage with grouped sections:

- Basic: enabled, name, type, capture mode, interval, pause.
- Recognition: keywords, language, OCR fields, similarity threshold, color tolerance.
- Region and target assets: region, template path, color, picker buttons.
- Action sequence: embedded action sequence editor.
- Legacy/default click compatibility: click mode, sink-after-click, mouse jitter, humanize mouse,
  click type, click target, custom coordinates.
- Chain: chain enabled, target, wait.
- Popup flow: enable checkbox always visible; all other popup controls hidden while disabled.

The saved group dictionary should still be produced by `dump_group()` with existing keys.

### Popup Visibility

When `popup_enabled` is unchecked:

- Hide popup-only mode.
- Hide popup title keyword.
- Hide popup wait appear/close and total timeout.
- Hide popup no-match action.
- Hide popup template editor and raw JSON storage area.

When checked, restore those controls and continue saving their values.

### Wheel Handling

Use focus-gated wheel behavior for:

- All `QSpinBox` and `QDoubleSpinBox` controls in the group editor and embedded action editor.
- All `QComboBox` controls in the group editor and embedded action editor.

Unfocused wheel events should be ignored so scrolling the editor does not accidentally change values.

## Data Flow

1. `load_group()` passes `g["actions"]` into the embedded action editor.
2. User edits typed action rows.
3. `dump_group()` reads actions from the embedded editor and writes the same `actions` list schema.
4. Runtime modules continue consuming the existing action dictionaries unchanged.
5. The raw JSON dialog remains a compatibility escape hatch and feeds the same embedded editor state.

## Testing Plan

Add focused offscreen Qt smoke tests for:

- Group editor no longer exposes visible action JSON by default.
- JSON button opens a raw JSON editor path and preserves action list roundtrip.
- Adding each action type creates a typed row and saves the expected action dictionary.
- Mouse rows expose only mouse fields; delay rows expose only wait seconds.
- Action reorder changes saved action order.
- Group editor popup controls are hidden when `popup_enabled` is false and visible when true.
- Combo boxes and spin boxes ignore wheel events without focus and respond with focus.
- Existing group editor roundtrip tests continue to pass.

## Out Of Scope

- Changing action runtime behavior.
- Removing legacy/default click fields from saved config.
- Reworking popup template editor internals unless required for embedded action reuse.
- Replacing QSS theme architecture.

## Self Review

- No placeholder requirements remain.
- Requirements preserve the existing action config schema and runtime behavior.
- Scope is limited to Qt editor widgets, layout, visibility, and tests.
- Popup hidden-state behavior is explicit: only the enable checkbox remains visible.
