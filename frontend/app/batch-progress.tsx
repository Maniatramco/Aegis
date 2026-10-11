"use client";
import {WorkflowStepper} from './workflow-stepper';
import { summarizeUploadBatch, documentJourneySteps, type UploadProgressItem } from "./batch-workflow";
import "./batch-progress.css";

const labels = { upload:"Upload", extract:"Read document", index:"Build index", ready:"Ready" };
export function BatchProgress({items,compact=false}:{items:UploadProgressItem[];compact?:boolean}) {
  const batch = summarizeUploadBatch(items);
  if (!batch.total) return null;
  const attention = `${batch.attention} ${batch.attention === 1 ? "needs" : "need"} attention`;
  const summary = batch.ready === batch.total ? "All documents are ready for questions." : batch.active > 0 ? `${batch.active} processing${batch.attention ? ` · ${attention}` : ""}. Progress follows completed stages.` : batch.attention ? `${attention}. Check the affected documents below.` : items.every(item=>!item.document&&item.status==='selected') ? "Ready to upload. Processing starts after you upload." : "Check the document statuses below.";
  return <section className={`batch-progress${compact ? " is-compact" : ""}`} aria-label="Batch upload workflow">
    <div className="batch-progress-heading"><strong>Document workflow</strong><span>{batch.ready} of {batch.total} ready</span></div>
    <div className="batch-progress-track" role="progressbar" aria-label="Batch processing progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={batch.progress} aria-valuetext={`${batch.ready} of ${batch.total} documents ready; ${batch.progress}% of workflow stages completed`}><span style={{width:`${batch.progress}%`}} /></div>
    <WorkflowStepper label="Document workflow steps" steps={documentJourneySteps(items)}/>
    <p className="batch-progress-summary" role="status">{summary}</p>
  </section>;
}
