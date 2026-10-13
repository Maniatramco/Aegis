export const uploadStages = ["upload", "extract", "index", "ready"] as const;
export type UploadStage = typeof uploadStages[number];
export type StageStatus = "completed" | "running" | "failed" | "waiting" | "unknown";
export type UploadProgressItem = {
  id: string; name: string; status: string; ready?: boolean; processing?: boolean; failed?: boolean; error?:string;
  document?: { id?:string; status?: string; requires_reindex?: boolean; error?:string };
  job?: { id?:string; status?: string; error?:string; workflow?: { current?: string; stages?: Record<string, { status?: string }> } };
};

export function uploadStageStatus(item: UploadProgressItem, stage: UploadStage): StageStatus {
  // The newest document state wins when document and job polls cross.
  if (item.ready) return "completed";
  if (!item.document) {
    if (stage !== "upload") return "waiting";
    if (item.status === "uploading") return "running";
    if (["invalid", "failed"].includes(item.status)) return "failed";
    return item.status === "uncertain" || item.status === "submitted" ? "unknown" : "waiting";
  }
  if (stage === "upload") return "completed";
  const workflow = item.job?.workflow;
  const actual = workflow?.stages?.[stage]?.status;
  if (item.failed && (workflow?.current === stage || (!workflow?.current && stage === "index"))) return "failed";
  // A requested rebuild cannot reuse completion from an older index job.
  if (item.processing && ["completed", "failed", "cancelled"].includes(item.job?.status || "")) return "unknown";
  if (actual === "completed" || actual === "running" || actual === "failed") return actual;
  if (stage === "ready") return "waiting";
  return actual === "blocked" || actual === "queued" ? "waiting" : "unknown";
}

export function summarizeUploadBatch(items: UploadProgressItem[]) {
  const stages = uploadStages.map(stage => {
    const statuses = items.map(item => uploadStageStatus(item, stage));
    const count = (status: StageStatus) => statuses.filter(value => value === status).length;
    const completed = count("completed"), running = count("running"), failed = count("failed"), unknown = count("unknown");
    const status: StageStatus = completed === items.length && items.length ? "completed" : running ? "running" : failed ? "failed" : unknown ? "unknown" : "waiting";
    return { stage, status, completed, running, failed, unknown };
  });
  const ready = items.filter(item => item.ready).length;
  const attention = items.filter(item => item.failed || (item.document?.requires_reindex && !item.processing && !item.ready) || ["invalid", "failed", "uncertain"].includes(item.status)).length;
  const active = items.filter(item => item.status === "uploading" || item.processing).length;
  return { stages, ready, attention, active, total:items.length,
    progress:items.length ? Math.floor(stages.reduce((sum,stage) => sum + stage.completed,0) / (items.length * uploadStages.length) * 100) : 0 };
}

// The reference's three stages group real upload/read, index and readiness
// transitions. Chat readiness is never inferred from an uploaded file alone.
export function documentJourneySteps(items: UploadProgressItem[]) {
  const {stages,total}=summarizeUploadBatch(items);
  const groups=[{id:'document',label:'Document',icon:'document',stages:['upload','extract']},
    {id:'knowledge',label:'Knowledge',icon:'knowledge',stages:['index']},
    {id:'chat',label:'AI Chat',icon:'chat',stages:['ready']}] as const;
  return groups.map(group=>{
    const members=stages.filter(stage=>group.stages.some(name=>name===stage.stage));
    const status=members.every(stage=>stage.status==='completed')?'completed':members.some(stage=>stage.status==='running')?'running':members.some(stage=>stage.status==='failed')?'failed':'pending';
    const completed=items.filter(item=>group.stages.every(stage=>uploadStageStatus(item,stage)==='completed')).length;
    return {id:group.id,label:group.label,icon:group.icon,status,detail:total>1?`${completed}/${total} done`:undefined};
  });
}

export function currentUploadStep(item: UploadProgressItem): string {
  if (item.ready) return "Ready for questions";
  if (item.status === "uncertain") return "Upload not confirmed";
  if (item.status === "invalid") return "File needs attention";
  if (item.status === "failed" && !item.document) return "Upload failed";
  if (item.document?.requires_reindex && !item.processing && !item.failed) return "Reindex required";
  const labels: Record<UploadStage,string> = { upload:"Uploading original", extract:"Reading document", index:"Building index", ready:"Finishing" };
  const failed = uploadStages.find(stage => uploadStageStatus(item,stage) === "failed");
  if (failed) return `${labels[failed]} failed`;
  const running = uploadStages.find(stage => uploadStageStatus(item,stage) === "running");
  if (running) return labels[running];
  if (!item.document) return item.status === "submitted" ? "Check dataset status" : "Ready to upload";
  return item.processing ? "Queued for processing" : "Status unavailable";
}

export function readableUploadError(error: string): string {
  if (/utf-?8.*(?:decode|invalid)|(?:decode|invalid).*utf-?8/i.test(error)) return "This TXT file is not valid UTF-8. Save a copy as UTF-8 and upload it again.";
  return error;
}
