# Frontend UX and Component Standard

Applies to all frontend work under `web/src/**/*`.

## Core UX Principles

- Keep visual language consistent with existing `FlowStudio` and config pages.
- Reuse existing components/styles before creating new variants.
- Prioritize predictable interaction: explicit user actions over implicit auto-trigger.

## Component Usage Rules

- **Help/Hint**: use `InfoTip` for inline help; do not add custom `?` buttons.
- **Confirmation**: use in-page modal style (`confirm-mask`, `confirm-dialog`) for destructive actions; avoid browser `confirm()`.
- **Buttons**: reuse existing classes (`btn`, `ghost`, `primary`, `danger`, `sm`) and keep hierarchy clear.
- **Inputs**: use shared input/select classes (`inp`, `sel`) and existing focus styles.
- **Feedback**: use lightweight in-context feedback (inline message, subtle pulse), avoid disruptive alerts.

## Destructive Action Pattern

1. Build precise confirmation text (scope + estimated impact if available).
2. Open unified modal.
3. Execute only after explicit confirm.
4. Clear pending state after action/cancel.

## Code Generation Checklist

- Did you reuse existing components before adding new UI?
- Does destructive flow avoid native dialogs?
- Are spacing, radius, border, and typography consistent with nearby pages?
- Does behavior match existing interaction expectations (especially Enter, clear, confirm)?
- Is mobile/narrow-width wrapping still usable?