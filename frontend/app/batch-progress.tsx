"use client";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { summarizeUploadBatch, type UploadProgressItem } from "./batch-workflow";
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
    <ol className="workflow-stages batch-stages">{batch.stages.map(stage => <li key={stage.stage} className={`stage-${stage.status}`}>
      <span className="stage-symbol">{stage.status === "completed" ? <CheckCircle2 size={21}/> : stage.status === "running" ? <Loader2 className="animate-spin" size={21}/> : stage.status === "failed" ? <AlertCircle size={21}/> : <span className="stage-dot"/>}</span>
      <strong>{labels[stage.stage]}</strong><small>{stage.completed}/{batch.total} done{stage.running > 0 && ` · ${stage.running} active`}{stage.failed > 0 && ` · ${stage.failed} failed`}{stage.unknown > 0 && ` · ${stage.unknown} checking`}</small>
    </li>)}</ol>
    <p className="batch-progress-summary" role="status">{summary}</p>
  </section>;
}
