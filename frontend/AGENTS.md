# Frontend workflow convention

For any workflow progress UI, use `app/workflow-stepper.tsx` and its shared stylesheet. Follow `../docs/WORKFLOW-DESIGN.md` and the latest saved data journey reference. Actual step names and live statuses are required. Keep the approved compact horizontal blue/white markers, checkmarks, dark-blue rotating ring and incoming particle flow consistent across all workflows. Do not create an independent stepper without an explicit user request to change the standard.

Use `app/agent-logo.tsx` for the Aegis Agent identity. Follow `../docs/AGENT-BRAND.md`; retain the original Aegis platform mark in the global header. Preserve legacy assistant route aliases when changing navigation.
