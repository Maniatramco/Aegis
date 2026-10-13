# Aegis Agent identity

The unified conversational workspace is named **Aegis Agent**. Its icon derives from the existing platform Aegis logo: the same rounded blue A silhouette and sculpted gradient, with a friendly white face and two blue eyes in the central opening. The platform logo stays in the global workspace header.

Use `frontend/app/agent-logo.tsx` for the agent navigation icon (24px), page title (28px), reply identity (24px) and welcome screen (64px). Decorative instances have empty alt text; standalone instances have an accessible label. The approved blue and white workflow standard remains in `WORKFLOW-DESIGN.md`.

The canonical route is `#Aegis%20Agent`. Existing `#Aegis%20Assistant` bookmarks redirect to this route. The retained Document Chat route is separate.

The floating workspace shortcut uses the shared agent logo inside a blue and white circular button with a small chat badge. It is hidden on the Aegis Agent page itself. On other workspace pages it stays at the lower right, moves above Review save controls, and opens the canonical agent route through normal navigation so unsaved-edit protection remains active. Hover or keyboard focus reveals its Aegis Agent label. The shortcut does not imply a running workflow.

## Asset provenance

Generated with the built-in image generation tool, transparent background, using `frontend/public/aegis-logo.png` as the brand reference. Original output preserved at `frontend/public/aegis-agent-logo-source-v2.png`; production asset is `frontend/public/aegis-agent-logo-v2.webp` (256px, lossless with alpha). Version 1 source and asset are retained as earlier explorations.

Final prompt:

> Create the Aegis Agent icon as a close derivative of the supplied existing Aegis brand logo. The input is the brand reference: retain the same distinctive rounded capital-A silhouette, curved broad blue legs, luminous cobalt/electric-blue palette and soft sculpted gradient treatment. Do not introduce a surrounding shield or replace the A silhouette. Change only the small central shield-shaped negative-space opening into a compact friendly intelligent-agent face: white protective face/mask inside that opening with two simple blue circular eyes. Keep the whole mark exceptionally simple and recognizable at 24px, professional and calm, no angry slanted eyes, no mascot body, no mouth or tiny circuitry. Preserve blue outer A structure and identity of the reference. One centered icon, square composition, close framing filling around 88%, genuinely transparent background. No text, wordmark, watermark, scene, drop shadow outside the mark, mockups or multiple variants. This is the agent-specific logo within the Aegis platform, so the A shape must match the reference closely.
