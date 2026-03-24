"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  CheckCircle2,
  Clock,
  Loader2,
  Pause,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { getTaskStatus, retryTaskArticles } from "@/lib/api";
import { toast } from "sonner";

const statusConfig = {
  completed: {
    icon: CheckCircle2,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    badge: "default" as const,
  },
  running: {
    icon: Loader2,
    color: "text-blue-600",
    bg: "bg-blue-50",
    badge: "secondary" as const,
  },
  paused: {
    icon: Pause,
    color: "text-amber-600",
    bg: "bg-amber-50",
    badge: "outline" as const,
  },
  pending: {
    icon: Clock,
    color: "text-gray-500",
    bg: "bg-gray-50",
    badge: "outline" as const,
  },
  partial: {
    icon: RotateCcw,
    color: "text-amber-700",
    bg: "bg-amber-50",
    badge: "secondary" as const,
  },
  failed: {
    icon: XCircle,
    color: "text-red-600",
    bg: "bg-red-50",
    badge: "destructive" as const,
  },
};

function summarizeChunkReport(
  chunkReport?: Array<{
    status: string;
    pmids: string[];
    chunk_index: number;
  }>
) {
  const summary = {
    completed: 0,
    running: 0,
    failed: 0,
    pending: 0,
    retryablePmids: [] as string[],
  };

  for (const chunk of chunkReport ?? []) {
    if (chunk.status === "completed") summary.completed += 1;
    else if (chunk.status === "running") summary.running += 1;
    else if (chunk.status === "failed") {
      summary.failed += 1;
      summary.retryablePmids.push(...chunk.pmids);
    } else {
      summary.pending += 1;
    }
  }

  summary.retryablePmids = Array.from(new Set(summary.retryablePmids));
  return summary;
}

export function TasksSection() {
  const [selectedTab, setSelectedTab] = useState("all");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [retryingMode, setRetryingMode] = useState<"failed" | "incomplete" | null>(null);
  const [selectedArticlePmids, setSelectedArticlePmids] = useState<string[]>([]);
  const { tasks, updateTask, addTask, setShowResults } = useAppStore();

  useEffect(() => {
    const runningTasks = tasks.filter((t) => t.status === "running" || t.status === "pending");

    if (runningTasks.length === 0) return;

    const interval = setInterval(async () => {
      for (const task of runningTasks) {
        try {
          const status = await getTaskStatus(task.id);

          updateTask(task.id, {
            status: status.status as any,
            progress: status.progress * 100,
            completed: Math.floor(status.progress * task.total),
            resultFile: status.result_file,
            message: status.message,
            error: status.status === "failed" ? status.message : undefined,
            fullTextReport: status.fulltext_report,
            citationReport: status.citation_report,
            extractionReport: status.extraction_report,
            chunkReport: status.chunk_report,
            articleReport: status.article_report,
          });

          if (status.status === "completed" && status.result_file) {
            toast.success(`Task ${task.id} completed!`);
            setShowResults(true);
          }

          if (status.status === "partial") {
            if (status.result_file) {
              setShowResults(true);
            }
            toast.error(`Task ${task.id} completed with partial failures.`);
          }

          if (status.status === "failed") {
            toast.error(`Task ${task.id} failed: ${status.message}`);
          }
        } catch (error) {
          console.error(`Failed to poll task ${task.id}:`, error);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [tasks, updateTask, setShowResults]);

  const filteredTasks = useMemo(
    () => tasks.filter((task) => (selectedTab === "all" ? true : task.status === selectedTab)),
    [selectedTab, tasks]
  );

  const activeTask = filteredTasks.find((task) => task.id === selectedTaskId) ?? filteredTasks[0] ?? null;
  const articleStatusSummary = useMemo(() => {
    const summary = {
      citationReady: 0,
      fulltextReady: 0,
      extractionSuccess: 0,
      extractionFailed: 0,
      incomplete: 0,
    };

    for (const article of activeTask?.articleReport ?? []) {
      if (article.citation_status === "success") summary.citationReady += 1;
      if (article.fulltext_status === "ready") summary.fulltextReady += 1;
      if (article.extraction_status === "success") summary.extractionSuccess += 1;
      if (article.extraction_status === "failed" || article.extraction_status === "missing") {
        summary.extractionFailed += 1;
      }
      if (article.result_status !== "full_table") summary.incomplete += 1;
    }

    return summary;
  }, [activeTask?.articleReport]);
  const chunkStatusSummary = useMemo(
    () => summarizeChunkReport(activeTask?.chunkReport),
    [activeTask?.chunkReport]
  );
  const authIssueMessage = useMemo(() => {
    const candidates = [
      activeTask?.message,
      activeTask?.error,
      ...(activeTask?.articleReport?.map((article) => article.error).filter(Boolean) ?? []),
    ].filter(Boolean) as string[];

    return (
      candidates.find((message) =>
        message.includes("Zhipu API authentication failed") ||
        message.includes("令牌已过期") ||
        message.includes("验证不正确")
      ) ?? null
    );
  }, [activeTask]);
  const detectedAuthIssueMessage = useMemo(() => {
    const candidates = [
      activeTask?.message,
      activeTask?.error,
      ...(activeTask?.articleReport?.map((article) => article.error).filter(Boolean) ?? []),
    ].filter(Boolean) as string[];

    return (
      candidates.find((message) =>
        message.includes("Zhipu API authentication failed") ||
        message.includes("401") ||
        message.toLowerCase().includes("token")
      ) ?? null
    );
  }, [activeTask]);
  const llmProgress = useMemo(() => {
    const attempted = activeTask?.extractionReport?.attempted ?? 0;
    const success = activeTask?.extractionReport?.success ?? 0;
    const failed = activeTask?.extractionReport?.failed ?? 0;
    const total = Math.max(
      activeTask?.fullTextReport?.downloaded ?? 0,
      attempted
    );

    return {
      total,
      completed: success + failed,
      percent: total > 0 ? ((success + failed) / total) * 100 : 0,
    };
  }, [activeTask]);
  const runningCount = tasks.filter((t) => t.status === "running").length;
  const allSelected = activeTask?.articleReport?.length
    ? activeTask.articleReport.every((article) => selectedArticlePmids.includes(article.pmid))
    : false;

  useEffect(() => {
    setSelectedArticlePmids([]);
  }, [activeTask?.id]);

  const handleRetry = async (mode: "failed" | "incomplete") => {
    if (!activeTask) return;

    try {
      setRetryingMode(mode);
      const response = await retryTaskArticles(activeTask.id, { mode });
      addTask({
        id: response.task_id,
        query: `${activeTask.query} (${mode} retry)`,
        pmids: [],
        status: "pending",
        progress: 0,
        total: response.article_count ?? 0,
        completed: 0,
        failed: 0,
        createdAt: new Date().toISOString(),
        message: response.message,
      });
      setSelectedTaskId(response.task_id);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create retry task");
    } finally {
      setRetryingMode(null);
    }
  };

  const handleRetrySelected = async () => {
    if (!activeTask || selectedArticlePmids.length === 0) return;

    try {
      setRetryingMode("incomplete");
      const response = await retryTaskArticles(activeTask.id, { pmids: selectedArticlePmids });
      addTask({
        id: response.task_id,
        query: `${activeTask.query} (selected retry)`,
        pmids: selectedArticlePmids,
        status: "pending",
        progress: 0,
        total: response.article_count ?? selectedArticlePmids.length,
        completed: 0,
        failed: 0,
        createdAt: new Date().toISOString(),
        message: response.message,
      });
      setSelectedTaskId(response.task_id);
      setSelectedArticlePmids([]);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create selected retry task");
    } finally {
      setRetryingMode(null);
    }
  };

  const handleRetryFailedChunks = async () => {
    if (!activeTask || chunkStatusSummary.retryablePmids.length === 0) return;

    try {
      setRetryingMode("failed");
      const response = await retryTaskArticles(activeTask.id, { pmids: chunkStatusSummary.retryablePmids });
      addTask({
        id: response.task_id,
        query: `${activeTask.query} (failed chunks retry)`,
        pmids: chunkStatusSummary.retryablePmids,
        status: "pending",
        progress: 0,
        total: response.article_count ?? chunkStatusSummary.retryablePmids.length,
        completed: 0,
        failed: 0,
        createdAt: new Date().toISOString(),
        message: response.message,
      });
      setSelectedTaskId(response.task_id);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to retry failed chunks");
    } finally {
      setRetryingMode(null);
    }
  };

  const getFailureAction = (reason: string) => {
    switch (reason) {
      case "request_failed":
        return "Retry the task. This usually points to a transient NCBI network issue.";
      case "not_available":
        return "Use metadata-only export for this article. PMC BioC full text is not available.";
      case "empty_content":
        return "Open the PMC article manually if needed. The response did not contain usable body text.";
      case "parse_error":
        return "Inspect the BioC structure or broaden the parser rules for this journal format.";
      default:
        return "Review the backend log for more detail before retrying.";
    }
  };

  if (tasks.length === 0) {
    return null;
  }

  return (
    <section id="tasks" className="py-20">
      <div className="container">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between mb-8">
          <div>
            <h2 className="font-serif text-3xl md:text-4xl font-normal mb-2">
              Processing Tasks
            </h2>
            <p className="text-muted-foreground">
              Review running jobs on the left and inspect detailed task progress on the right.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {runningCount > 0 && (
              <Badge variant="secondary" className="gap-1.5 font-normal">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                {runningCount} Running
              </Badge>
            )}
            <Badge variant="outline" className="font-normal">
              {tasks.length} Total Tasks
            </Badge>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="flex min-h-[640px] flex-col border-border/50">
            <CardHeader className="space-y-4">
              <div>
                <CardTitle className="text-lg">Task Queue</CardTitle>
                <CardDescription>Select a task to inspect its full progress.</CardDescription>
              </div>
              <Tabs value={selectedTab} onValueChange={setSelectedTab}>
                <TabsList className="h-9 w-full grid grid-cols-4">
                  <TabsTrigger value="all" className="text-sm">All</TabsTrigger>
                  <TabsTrigger value="running" className="text-sm">Running</TabsTrigger>
                  <TabsTrigger value="completed" className="text-sm">Completed</TabsTrigger>
                  <TabsTrigger value="failed" className="text-sm">Failed</TabsTrigger>
                </TabsList>
              </Tabs>
            </CardHeader>

            <CardContent className="flex min-h-0 flex-1 flex-col gap-3 pt-0">
              <ScrollArea
                className={`pr-3 ${
                  activeTask?.chunkReport?.length ? "h-[320px]" : "flex-1 min-h-0"
                }`}
              >
                <div className="space-y-3">
                  {filteredTasks.map((task) => {
                    const config = statusConfig[task.status as keyof typeof statusConfig];
                    const StatusIcon = config.icon;
                    const isActive = activeTask?.id === task.id;
                    const taskChunkSummary = summarizeChunkReport(task.chunkReport);
                    const hasChunkReport = Boolean(task.chunkReport?.length);

                    return (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelectedTaskId(task.id)}
                        className={`w-full min-w-0 overflow-hidden rounded-xl border p-4 text-left transition-colors ${
                          isActive
                            ? "border-primary/40 bg-muted/50"
                            : "border-border/50 bg-background hover:bg-muted/30"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex items-start gap-3">
                            <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${config.bg}`}>
                              <StatusIcon
                                className={`h-4 w-4 ${config.color} ${task.status === "running" ? "animate-spin" : ""}`}
                              />
                            </div>
                            <div className="min-w-0 space-y-1">
                              <div className="line-clamp-2 break-words pr-1 font-medium leading-5">
                                {task.query}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {new Date(task.createdAt).toLocaleString()}
                              </div>
                              {task.message && (
                                <div className="line-clamp-2 break-words text-xs text-muted-foreground">
                                  {task.message}
                                </div>
                              )}
                            </div>
                          </div>
                          <Badge variant={config.badge} className="shrink-0 capitalize font-normal">
                            {task.status}
                          </Badge>
                        </div>
                        <div className="mt-3 space-y-2">
                          <Progress value={task.progress} className="h-1.5" />
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>{Math.round(task.progress)}%</span>
                            <span>{task.completed}/{task.total} articles</span>
                          </div>
                          {hasChunkReport && (
                            <div className="rounded-lg border border-border/50 bg-muted/30 px-3 py-2">
                              <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                                <span>Chunk Progress</span>
                                <span>{task.chunkReport?.length} batches</span>
                              </div>
                              <div className="grid grid-cols-4 gap-2 text-left text-[11px]">
                                <div>
                                  <div className="text-muted-foreground">Done</div>
                                  <div className="font-medium text-foreground">{taskChunkSummary.completed}</div>
                                </div>
                                <div>
                                  <div className="text-muted-foreground">Run</div>
                                  <div className="font-medium text-foreground">{taskChunkSummary.running}</div>
                                </div>
                                <div>
                                  <div className="text-muted-foreground">Fail</div>
                                  <div className="font-medium text-foreground">{taskChunkSummary.failed}</div>
                                </div>
                                <div>
                                  <div className="text-muted-foreground">Wait</div>
                                  <div className="font-medium text-foreground">{taskChunkSummary.pending}</div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      </button>
                    );
                  })}
                  {filteredTasks.length === 0 && (
                    <div className="rounded-xl border border-dashed border-border/60 p-6 text-sm text-muted-foreground">
                      No tasks in this view.
                    </div>
                  )}
                </div>
              </ScrollArea>

              {activeTask?.chunkReport && activeTask.chunkReport.length > 0 && (
                <div className="rounded-xl border border-border/50 bg-background p-4">
                  <div className="space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-medium">Chunk Progress</h3>
                      <Badge variant="outline" className="font-normal">
                        {activeTask.chunkReport.length} batches
                      </Badge>
                    </div>
                    <p className="text-xs leading-5 text-muted-foreground">
                      Batch-level progress stays in the left task panel so you can monitor queue health without leaving the task list.
                    </p>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                      <div className="text-[11px] text-muted-foreground">Completed</div>
                      <div className="mt-1 text-lg font-semibold">{chunkStatusSummary.completed}</div>
                    </div>
                    <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                      <div className="text-[11px] text-muted-foreground">Running</div>
                      <div className="mt-1 text-lg font-semibold">{chunkStatusSummary.running}</div>
                    </div>
                    <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                      <div className="text-[11px] text-muted-foreground">Failed</div>
                      <div className="mt-1 text-lg font-semibold">{chunkStatusSummary.failed}</div>
                    </div>
                    <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                      <div className="text-[11px] text-muted-foreground">Pending</div>
                      <div className="mt-1 text-lg font-semibold">{chunkStatusSummary.pending}</div>
                    </div>
                  </div>

                  <ScrollArea className="mt-4 h-[220px] pr-3">
                    <div className="space-y-3">
                      {activeTask.chunkReport.map((chunk) => (
                        <div
                          key={`${activeTask.id}-queue-chunk-${chunk.chunk_index}`}
                          className="rounded-lg border border-border/50 p-3 space-y-2"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="font-normal">
                              Chunk {chunk.chunk_index}
                            </Badge>
                            <Badge variant="secondary" className="font-normal capitalize">
                              {chunk.status}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {chunk.article_count} articles
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
                            <div>full text: {chunk.fulltext_downloaded}</div>
                            <div>cache hits: {chunk.cached_hits}</div>
                            <div>success: {chunk.extraction_success}</div>
                            <div>failed: {chunk.extraction_failed}</div>
                          </div>
                          <div className="text-xs leading-5 text-muted-foreground">
                            <span className="break-words whitespace-pre-wrap">{chunk.message}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/50 min-h-[640px]">
            {!activeTask ? (
              <CardContent className="flex min-h-[640px] items-center justify-center text-sm text-muted-foreground">
                Select a task from the queue to inspect its progress.
              </CardContent>
            ) : (
              <>
                <CardHeader className="space-y-5">
                  <div className="flex flex-col gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-3">
                        <CardTitle className="text-xl">{activeTask.query}</CardTitle>
                        <Badge
                          variant={statusConfig[activeTask.status as keyof typeof statusConfig].badge}
                          className="capitalize font-normal"
                        >
                          {activeTask.status}
                        </Badge>
                      </div>
                      <CardDescription>
                        Task ID: {activeTask.id}
                      </CardDescription>
                      <div className="text-sm text-muted-foreground">
                        <span className="break-all">Created {new Date(activeTask.createdAt).toLocaleString()}</span>
                      </div>
                    </div>
                    {activeTask.articleReport && activeTask.articleReport.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleRetryFailedChunks}
                          disabled={retryingMode !== null || chunkStatusSummary.retryablePmids.length === 0}
                          className="gap-2"
                        >
                          <RotateCcw className="h-4 w-4" />
                          Retry Failed Chunks
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleRetry("failed")}
                          disabled={retryingMode !== null || articleStatusSummary.extractionFailed === 0}
                          className="gap-2"
                        >
                          <RotateCcw className={`h-4 w-4 ${retryingMode === "failed" ? "animate-spin" : ""}`} />
                          Retry Failed Articles
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleRetry("incomplete")}
                          disabled={retryingMode !== null || articleStatusSummary.incomplete === 0}
                          className="gap-2"
                        >
                          <RotateCcw className={`h-4 w-4 ${retryingMode === "incomplete" ? "animate-spin" : ""}`} />
                          Retry Incomplete Articles
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleRetrySelected}
                          disabled={retryingMode !== null || selectedArticlePmids.length === 0}
                          className="gap-2"
                        >
                          <RotateCcw className="h-4 w-4" />
                          Retry Selected ({selectedArticlePmids.length})
                        </Button>
                      </div>
                    )}
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                      <div className="text-xs text-muted-foreground">Progress</div>
                      <div className="mt-2 text-2xl font-semibold">{Math.round(activeTask.progress)}%</div>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                      <div className="text-xs text-muted-foreground">Articles</div>
                      <div className="mt-2 text-2xl font-semibold">
                        {activeTask.completed}/{activeTask.total}
                      </div>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                      <div className="text-xs text-muted-foreground">Current Stage</div>
                      <div className="mt-2 text-sm font-medium leading-6">
                        <span className="break-words whitespace-pre-wrap">
                          {activeTask.message || "Waiting for updates"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Progress value={activeTask.progress} className="h-2" />
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{Math.round(activeTask.progress)}% complete</span>
                      <span>{activeTask.completed} of {activeTask.total} articles processed</span>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-6">
                  {detectedAuthIssueMessage && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      <span className="break-words whitespace-pre-wrap">
                        Zhipu authentication issue detected: {detectedAuthIssueMessage}
                      </span>
                    </div>
                  )}

                  {activeTask.articleReport && activeTask.articleReport.length > 0 && (
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-sm font-medium">Article Stage Status</h3>
                        <p className="text-sm text-muted-foreground">
                          Fine-grained article progress that survives backend restarts.
                        </p>
                      </div>

                      <div className="grid gap-4 md:grid-cols-5">
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Citation Ready</div>
                          <div className="mt-2 text-xl font-semibold">{articleStatusSummary.citationReady}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Full Text Ready</div>
                          <div className="mt-2 text-xl font-semibold">{articleStatusSummary.fulltextReady}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Extraction Success</div>
                          <div className="mt-2 text-xl font-semibold">{articleStatusSummary.extractionSuccess}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Extraction Failed</div>
                          <div className="mt-2 text-xl font-semibold">{articleStatusSummary.extractionFailed}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Incomplete</div>
                          <div className="mt-2 text-xl font-semibold">{articleStatusSummary.incomplete}</div>
                        </div>
                      </div>

                      <div className="rounded-xl border border-border/50 bg-background p-4 overflow-auto">
                        <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-3">
                          <label className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
                            <Checkbox
                              checked={allSelected}
                              onCheckedChange={(checked) => {
                                setSelectedArticlePmids(
                                  checked
                                    ? activeTask.articleReport?.map((article) => article.pmid) ?? []
                                    : []
                                );
                              }}
                            />
                            <span className="break-words">Select all visible articles</span>
                          </label>
                          {selectedArticlePmids.length > 0 && (
                            <span className="break-words text-xs text-muted-foreground">
                              {selectedArticlePmids.length} selected for retry
                            </span>
                          )}
                        </div>
                        <ScrollArea className="max-h-[280px] w-full pr-3">
                          <div className="space-y-3">
                            {activeTask.articleReport.map((article) => (
                              <div key={article.pmid} className="min-w-0 rounded-lg border border-border/50 p-4 space-y-2">
                                <div className="flex min-w-0 flex-wrap items-center gap-2">
                                  <Checkbox
                                    checked={selectedArticlePmids.includes(article.pmid)}
                                    onCheckedChange={(checked) => {
                                      setSelectedArticlePmids((current) =>
                                        checked
                                          ? Array.from(new Set([...current, article.pmid]))
                                          : current.filter((pmid) => pmid !== article.pmid)
                                      );
                                    }}
                                  />
                                  <span className="min-w-0 break-words font-medium">{article.title || article.pmid}</span>
                                  <Badge variant="outline" className="font-normal">
                                    PMID {article.pmid}
                                  </Badge>
                                  {article.pmcid && (
                                    <Badge variant="outline" className="font-normal">
                                      {article.pmcid}
                                    </Badge>
                                  )}
                                </div>
                                <div className="flex flex-wrap gap-2 text-xs">
                                  <Badge variant="secondary" className="font-normal">
                                    citation: {article.citation_status || "pending"}
                                  </Badge>
                                  <Badge variant="secondary" className="font-normal">
                                    full text: {article.fulltext_status}
                                  </Badge>
                                  <Badge variant="secondary" className="font-normal">
                                    oa pdf: {article.oa_pdf_status || "pending"}
                                  </Badge>
                                  <Badge variant="secondary" className="font-normal">
                                    extraction: {article.extraction_status}
                                  </Badge>
                                  <Badge variant="outline" className="font-normal">
                                    result: {article.result_status}
                                  </Badge>
                                </div>
                                {article.error && (
                                  <div className="break-words whitespace-pre-wrap text-sm text-muted-foreground">
                                    {article.error}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </ScrollArea>
                      </div>
                    </div>
                  )}

                  {activeTask.extractionReport && (
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-sm font-medium">Extraction Cache Summary</h3>
                        <p className="text-sm text-muted-foreground">
                          How much LLM work was reused versus freshly executed.
                        </p>
                      </div>

                      {llmProgress.total > 0 && (
                        <div className="rounded-xl border border-amber-200/70 bg-amber-50/50 p-4">
                          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                            <span className="font-medium text-amber-900">LLM Parsing Progress</span>
                            <span className="text-amber-800">
                              {llmProgress.completed}/{llmProgress.total}
                            </span>
                          </div>
                          <Progress value={llmProgress.percent} className="h-2" />
                        </div>
                      )}

                      <div className="grid gap-4 md:grid-cols-5">
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Attempted</div>
                          <div className="mt-2 text-xl font-semibold">{activeTask.extractionReport.attempted}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Cache Hits</div>
                          <div className="mt-2 text-xl font-semibold">{activeTask.extractionReport.cached_hits}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Fresh Runs</div>
                          <div className="mt-2 text-xl font-semibold">{activeTask.extractionReport.fresh_runs}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Success</div>
                          <div className="mt-2 text-xl font-semibold">{activeTask.extractionReport.success}</div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Failed</div>
                          <div className="mt-2 text-xl font-semibold">{activeTask.extractionReport.failed}</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeTask.citationReport && (
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-sm font-medium">Citation Status</h3>
                        <p className="text-sm text-muted-foreground">
                          Status of the optional cited-by and reference link retrieval.
                        </p>
                      </div>

                      <div className="grid gap-4 md:grid-cols-4">
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Mode</div>
                          <div className="mt-2 text-sm font-medium capitalize">
                            {activeTask.citationReport.enabled ? activeTask.citationReport.status : "disabled"}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Cited-by Links</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.citationReport.cited_by_total}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Reference Links</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.citationReport.references_total}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Link Status</div>
                          <div className="mt-2 text-sm font-medium">
                            cited-by: {activeTask.citationReport.cited_by_status}
                            <br />
                            refs: {activeTask.citationReport.references_status}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-xl border border-border/50 bg-background px-4 py-3 text-sm text-muted-foreground">
                        {activeTask.citationReport.message}
                      </div>
                    </div>
                  )}

                  {activeTask.fullTextReport?.pmc_candidates ? (
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-sm font-medium">Full-text Download Summary</h3>
                        <p className="text-sm text-muted-foreground">
                          Detailed diagnostics for PMC download and fallback handling.
                        </p>
                      </div>

                      <div className="grid gap-4 md:grid-cols-5">
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">PMC Candidates</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.fullTextReport.pmc_candidates}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Downloaded</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.fullTextReport.downloaded}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Fallback Used</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.fullTextReport.fallback_used}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Cache Hits</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.fullTextReport.cache_hits}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background px-4 py-3">
                          <div className="text-xs text-muted-foreground">Failed</div>
                          <div className="mt-2 text-xl font-semibold">
                            {activeTask.fullTextReport.failed}
                          </div>
                        </div>
                      </div>

                      {Object.keys(activeTask.fullTextReport.failure_counts).length > 0 && (
                        <div className="rounded-xl border border-border/50 bg-background p-4 space-y-3">
                          <div className="text-sm font-medium">Failure Breakdown</div>
                          <div className="space-y-2">
                            {Object.entries(activeTask.fullTextReport.failure_counts).map(([reason, count]) => (
                              <div key={reason} className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">
                                  {activeTask.fullTextReport?.failure_labels[reason] || reason}
                                </span>
                                <span className="font-medium">{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {activeTask.fullTextReport.failed_items.length > 0 && (
                        <div className="min-w-0 overflow-hidden rounded-xl border border-border/50 bg-background p-4 space-y-4">
                          <div className="text-sm font-medium">Failed PMC Articles</div>
                          <ScrollArea className="h-[240px] w-full pr-3">
                            <div className="space-y-4">
                              {activeTask.fullTextReport.failed_items.map((item) => (
                                <div key={item.pmcid} className="min-w-0 rounded-lg border border-border/50 p-4 space-y-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="font-medium">{item.pmcid}</span>
                                    <Badge variant="outline" className="font-normal">
                                      {activeTask.fullTextReport?.failure_labels[item.reason] || item.reason}
                                    </Badge>
                                  </div>
                                  <div className="break-words whitespace-pre-wrap text-sm text-muted-foreground">
                                    {item.message || "No detailed backend message available."}
                                  </div>
                                  <div className="break-words whitespace-pre-wrap text-sm text-muted-foreground">
                                    Suggested action: {getFailureAction(item.reason)}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </ScrollArea>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-border/60 p-6 text-sm text-muted-foreground">
                      Full-text diagnostics will appear here once the task reaches the download stage.
                    </div>
                  )}
                </CardContent>
              </>
            )}
          </Card>
        </div>
      </div>
    </section>
  );
}
