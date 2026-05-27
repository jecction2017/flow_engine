import type { FlowRunSummary } from "@/api/flowRuns";

/** Per-deployment run sequence shown in UI (not the global PK). */
export function deployRunNo(run: Pick<FlowRunSummary, "run_no" | "id">): number {
  const n = run.run_no;
  return typeof n === "number" && n > 0 ? n : run.id;
}

export function formatDeployRunNo(run: Pick<FlowRunSummary, "run_no" | "id">): string {
  return `#${deployRunNo(run)}`;
}
