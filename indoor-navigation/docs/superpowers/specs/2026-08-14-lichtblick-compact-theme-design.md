# Compact Lichtblick Control Panel Design

**Date:** 2026-08-14

**Status:** approved in conversation

## Problem

The Robot Control extension currently looks visually separate from Lichtblick because its CSS forces a branded dark gradient and oversized pale cards even when Lichtblick is using its light theme. At a 2048×1152 application viewport with the panel occupying the right rail, the Quick Actions card falls below the visible panel area.

## Design

Use the `renderState.colorScheme` class already supplied by the adapter as the theme boundary. Light mode uses Lichtblick-like neutral surfaces, subtle gray borders, dark text, and the existing teal only as an action/status accent. Dark mode uses neutral dark surfaces rather than a decorative gradient. The root has `height: 100%` and `overflow-y: auto`, so every control remains reachable at smaller heights.

Compress the existing hierarchy without hiding or collapsing controls:

- reduce outer padding, card gaps, card padding, corner radii, and shadows;
- put the panel title and mode on one compact row;
- reduce WASD keys to a dense three-column cluster;
- reduce headings, pills, labels, inputs, and action buttons while retaining readable labels and focus rings;
- keep map actions in two-column rows at the current right-rail width;
- retain the existing single-column narrow-width fallback;
- keep Quick Actions fully visible at the screenshot-sized viewport, with additional vertical room below it.

No ROS behavior, layout split percentage, extension identity, control labels, enablement rules, or safety semantics change.

## Alternatives rejected

1. Keep the branded dark gradient and only shrink spacing. This would fix clipping but preserve the theme mismatch.
2. Collapse Maps or Quick Actions into accordions. This creates more capacity but violates the requirement that all buttons remain visible.
3. Increase the right rail width. This reduces the primary map area and does not solve vertical growth as more controls are added.

## Verification

- Existing component, adapter, drive, configuration, build, lint, and package tests remain green.
- Before the CSS change, a real bundled-viewer check at the screenshot-sized viewport must demonstrate that the panel content exceeds its visible height or Quick Actions is clipped.
- After the change, the same viewport must show all nine buttons and the bottom of Quick Actions without scrolling.
- Light mode background/card/text colors must be neutral and visually aligned with the surrounding Lichtblick panel; dark mode must remain readable.
- The complete indoor-navigation smoke test remains green because the deployment artifact and container are rebuilt.
