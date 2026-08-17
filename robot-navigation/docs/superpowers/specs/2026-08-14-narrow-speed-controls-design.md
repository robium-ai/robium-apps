# Narrow Robot Control and Speed Controls Design

## Goal

Make Robot Control useful in a narrower Lichtblick right rail while adding direct speed adjustment for manual driving.

## Layout and copy

- Change the mapping layout from a 72/28 split to a 76/24 split.
- Keep the internal `Robot Control` title, current mode pill, section titles, field labels, and action labels.
- Remove the four uppercase eyebrow lines, the movement speed badge, the ROS readiness badge, all instructional hints, and the Forward/Left/Backward/Right captions inside WASD buttons.
- Keep accessible direction names through each button's existing `aria-label`.
- Retain the mapping inputs, map selector, all action buttons, and status/error messages.

## Speed controls

Add two range inputs at the top of Movement:

- Forward speed: `0.05`–`0.50` m/s, step `0.05`.
- Turn speed: `0.10`–`1.50` rad/s, step `0.10`.

Each slider shows its current value in its visible label. Changing a slider calls the adapter's existing `updateConfig` path, which normalizes and saves panel state and rebuilds the drive controller so the next WASD command uses the new speed.

## Compatibility and safety

- ROS topics, services, parameters, publish rate, and mapping behavior remain unchanged.
- The Stop robot action remains visually prominent.
- Existing configurations continue to load; values outside the slider range display at the nearest supported endpoint and are saved only after user interaction.
- Dark and light theme tokens remain unchanged.

## Verification

- Component tests verify the reduced copy, accessible sliders, and persisted speed updates.
- Layout tests verify the 76/24 split.
- Extension lint/build/package and the real bundled Lichtblick view verify the narrow rendering.
- The two-goal navigation smoke remains the application regression gate.
