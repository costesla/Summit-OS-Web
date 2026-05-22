/**
 * Shared Summit Intelligence Async & Resilient Error Handling Utilities
 */

/**
 * Classifies whether an error is transient/backgroundable, such as proxy gateway timeouts,
 * network hiccups, or CORS errors during heavy operations.
 */
export function isBackgroundableError(err: unknown): boolean {
  if (!err) return false;
  
  const msg = err instanceof Error ? err.message : String(err);
  const normalized = msg.toLowerCase();
  
  return (
    normalized.includes("timeout_expected") ||
    normalized.includes("failed to fetch") ||
    normalized.includes("networkerror") ||
    normalized.includes("request timeout") ||
    normalized.includes("network timeout")
  );
}

/**
 * Development-only console error logging wrapper.
 */
export function devDebugError(err: unknown): void {
  // Check if we are in node or vite env
  const isDev = 
    (typeof process !== "undefined" && process.env?.NODE_ENV !== "production") ||
    (typeof import.meta !== "undefined" && (import.meta as any).env?.DEV);

  if (isDev) {
    console.error("[DEBUG] Full error object:", err);
  }
}

/**
 * Returns standardized log lines to display in the Intelligence Console immediately when 
 * an asynchronous background job is successfully scheduled.
 */
export function getAsyncExecutionLogs(jobId: string): string[] {
  return [
    `> Background job started`,
    `> Job ID: ${jobId}`,
    `> Processing time varies based on workload`,
    `> Most scans complete within ~1–2 minutes`,
    `> Refresh or monitor status to view results`
  ];
}

/**
 * Resilient, failure-tolerant job status polling helper.
 * Polls the job status API on the backend and triggers callbacks on state changes.
 */
export function pollJobStatus(
  apiBase: string,
  jobId: string,
  onUpdate: (logs: string[]) => void,
  onComplete: (result: any) => void,
  onFailure: (error: string) => void
): () => void {
  let intervalId: any = null;
  let consecutiveErrors = 0;
  const maxConsecutiveErrors = 5;
  let isStopped = false;

  const checkStatus = async () => {
    if (isStopped) return;

    try {
      const resp = await fetch(`${apiBase}/job-status/${jobId}`, {
        cache: "no-store",
        headers: { "Accept": "application/json" }
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const data = await resp.json();
      consecutiveErrors = 0; // reset on success

      if (data.logs && Array.isArray(data.logs)) {
        onUpdate(data.logs);
      }

      if (data.status === "completed") {
        stop();
        onComplete(data);
      } else if (data.status === "failed") {
        stop();
        onFailure(data.error || "Background job execution failed.");
      }
    } catch (err: unknown) {
      consecutiveErrors++;
      devDebugError(err);
      
      // If we have exceeded maximum consecutive errors, fail the polling.
      // Otherwise, we silently ignore transient network hiccups and retry.
      if (consecutiveErrors >= maxConsecutiveErrors) {
        stop();
        onFailure(`Connection to background job tracker lost after ${maxConsecutiveErrors} attempts.`);
      }
    }
  };

  const stop = () => {
    isStopped = true;
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  };

  // Run immediately, then poll every 2.5 seconds
  checkStatus();
  intervalId = setInterval(checkStatus, 2500);

  // Return unsubscribe/stop function
  return stop;
}
