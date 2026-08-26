# Final RunPod integration smoke

Date: 2026-08-26 (UTC)

This is the issue #69 final private RunPod flow. It validates the live image and
control-plane integration; it does not replace or alter the immutable 20-episode
evaluation at Hugging Face revision
`d9908eb717d3e8d62ca7ba0820a825daf36fa7c0`.

## Immutable inputs

| Item | Value |
| --- | --- |
| Application commit used to build the live image | `43f1a8c` |
| Cloud Build | [`5ea0ee45-8353-4c54-8496-8ee4eaa3d44e`](https://console.cloud.google.com/cloud-build/builds/5ea0ee45-8353-4c54-8496-8ee4eaa3d44e?project=902570464351) |
| Live image | `us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:4613c5229d88d7e4bb8ce055f92db3cd71d33077a9ab1efe33c18b4bf52a606a` |
| RunPod template | `e56b2xl1y1` |
| Network volume | `68s0bxbv7p`, `US-KS-2`, mounted at `/models` |
| GPU | one `NVIDIA RTX PRO 4500 Blackwell Server Edition`, Secure Cloud, $0.72/hour |
| Controller image | `us-central1-docker.pkg.dev/robium-prod/robium/demo-robot-navigation-control@sha256:f3c93696165d40507150f18fe0d2371c2b3a0cca6e3e7fc8ec0c77b1a86a3ea3` |
| Controller Cloud Build | [`d8ed9611-ebf3-4418-b3da-22b76e2848c3`](https://console.cloud.google.com/cloud-build/builds/d8ed9611-ebf3-4418-b3da-22b76e2848c3?project=902570464351) |

## Measured flow

The controller created RunPod Pod `yqqvxujoq78b37` for internal session
`9ee841775796f315c556a7` at approximately 07:47 UTC. It reached `READY` at
07:50:13 UTC after the offline checkpoint load. The gateway reported a numeric
ready-window countdown (`remaining_s=562` on first check), proving that the Pod
was running the rebuilt image with the ten-minute post-ready expiry behavior.

| Gate | Result |
| --- | --- |
| Authorized capability status | HTTP 200 |
| Unrelated root | HTTP 404 |
| Missing capability | HTTP 404 |
| Foreign capability | HTTP 404 |
| Capability-scoped UI | HTTP 200 |
| Capability claim | HTTP 200 |
| Canonical state-0 rollout | PASS: simulator success, seed 1000, 73 steps, 74 genuine frames, 3.854 seconds |
| Active state-1 cancellation | PASS: cancellation acknowledged, seed 1001, stopped after 31 steps/32 frames and 1.243 seconds |
| Visitor stop | HTTP 204 |
| Confirmed deletion | PASS: authoritative RunPod Pod list returned `[]` |

The RunPod billing aggregation had not yet emitted the deleted Pods when checked,
so no per-Pod charge is invented here. Account balance after the smoke was
`$19.5774215665`; the only continuing spend was the retained network volume at
`$0.002/hour`. Budget reservations were released on deletion.

One earlier smoke Pod exposed a stale live image pin because its status lacked
`remaining_s`. It was deleted, the image was rebuilt from the current gateway
commit, and every result above comes from the replacement digest
`sha256:4613c522…606a`. No Pod remained after either attempt.

## Production enablement smoke

The operator explicitly approved production live sessions on 2026-08-26. The
controller revision `demo-robot-navigation-control-00008-cus` and final site
revision `robium-site-00034-nox` were promoted by exact revision ID. The final
site image is
`us-central1-docker.pkg.dev/robium-prod/robium/site@sha256:1af8c4db07c4bb7cba358d5440217bd16e089b4e0927bc7932d3c029b79e3a63`;
its Cloud Build is
[`703eaecc-4324-4ddd-86bd-8893d49a7552`](https://console.cloud.google.com/cloud-build/builds/703eaecc-4324-4ddd-86bd-8893d49a7552?project=902570464351).

The public controller created Pod `c74qvd52y74rm6` for session
`a99c53d8a3ad0526140fcb`. It reached `READY`, reported `remaining_s=565`, and
passed root/missing/foreign isolation (404), scoped status/UI/claim (200), a
canonical state-0 success (75 steps, 76 frames, 3.439 seconds), and active
state-1 cancellation. The visitor DELETE returned 204 and the authoritative
RunPod list immediately returned zero active Pods. The budget reservation was
released; provider billing was still delayed at the final check, so no
per-session charge is invented. Account balance was `$19.5277963445`; continuing
idle spend was only the retained network volume at `$0.002/hour`.

The production browser showed `vla-live-build`, phase `IDLE`, and an enabled
“Start private session” control after cleanup. Production remains enabled under
the one-Pod fleet cap, ten-minute ready window, and $5 UTC-day ledger.
