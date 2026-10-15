# Frontend workflow convention

For any workflow progress UI, use `app/workflow-stepper.tsx` and its shared stylesheet. Follow the section Maintain the application and approved design in the [single handover](../ags_docs/Aegis_Architecture_and_Deployment_Handover.docx) and the [approved workflow reference](../ags_docs/ags_assets/workflow-stepper-reference.png). Actual step names and live statuses are required. Keep the approved compact horizontal blue/white markers, checkmarks, dark-blue rotating ring and incoming particle flow consistent across all workflows. Do not create an independent stepper without an explicit user request to change the standard.

Use `app/agent-logo.tsx` for the Aegis Agent identity and the same handover section. Retain the original Aegis platform mark in the global header. Preserve legacy assistant route aliases when changing navigation.
