type Job = Record<string, any>;
const ACTIVE = new Set(['queued', 'running', 'held']);

// Completed history is loaded once by the workspace, never polled for progress.
export function pendingJobIds(jobs: Job[]): string {
  return [...new Set(jobs.filter(job => ACTIVE.has(job.status)).map(job => job.id))]
    .sort().slice(0, 120).join(',');
}

export function mergeJobUpdates(existing: Job[], updates: Job[]): Job[] {
  const byId = new Map(existing.map(job => [job.id, job]));
  for (const job of updates) byId.set(job.id, job);
  return [...byId.values()];
}
