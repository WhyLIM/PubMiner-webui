"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  XCircle,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { getTaskStatus } from "@/lib/api";
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
  failed: {
    icon: XCircle,
    color: "text-red-600",
    bg: "bg-red-50",
    badge: "destructive" as const,
  },
};

export function TasksSection() {
  const [selectedTab, setSelectedTab] = useState("all");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const { tasks, updateTask, setShowResults } = useAppStore();

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
            articleReport: status.article_report,
          });

          if (status.status === "completed" && status.result_file) {
            toast.success(`Task ${task.id} completed!`);
            setShowResults(true);
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
  const runningCount = tasks.filter((t) => t.status === "running").length;

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
          <Card className="border-border/50">
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

            <CardContent className="pt-0">
              <ScrollArea className="h-[560px] pr-3">
                <div className="space-y-3">
                  {filteredTasks.map((task) => {
                    const config = statusConfig[task.status as keyof typeof statusConfig];
                    const StatusIcon = config.icon;
                    const isActive = activeTask?.id === task.id;

                    return (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelectedTaskId(task.id)}
                        className={`w-full rounded-xl border p-4 text-left transition-colors ${
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
                              <div className="truncate font-medium">{task.query}</div>
                              <div className="text-xs text-muted-foreground">
                                {new Date(task.createdAt).toLocaleString()}
                              </div>
                              {task.message && (
                                <div className="line-clamp-2 text-xs text-muted-foreground">
                                  {task.message}
                                </div>
                              )}
                            </div>
                          </div>
                          <Badge variant={config.badge} className="capitalize font-normal">
                            {task.status}
                          </Badge>
                        </div>
                        <div className="mt-3 space-y-2">
                          <Progress value={task.progress} className="h-1.5" />
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>{Math.round(task.progress)}%</span>
                            <span>{task.completed}/{task.total} articles</span>
                          </div>
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
                        Created {new Date(activeTask.createdAt).toLocaleString()}
                      </div>
                    </div>
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
                        {activeTask.message || "Waiting for updates"}
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
                        <div className="rounded-xl border border-border/50 bg-background p-4 space-y-4">
                          <div className="text-sm font-medium">Failed PMC Articles</div>
                          <ScrollArea className="max-h-[210px] pr-3">
                            <div className="space-y-4">
                              {activeTask.fullTextReport.failed_items.map((item) => (
                                <div key={item.pmcid} className="rounded-lg border border-border/50 p-4 space-y-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="font-medium">{item.pmcid}</span>
                                    <Badge variant="outline" className="font-normal">
                                      {activeTask.fullTextReport?.failure_labels[item.reason] || item.reason}
                                    </Badge>
                                  </div>
                                  <div className="text-sm text-muted-foreground">
                                    {item.message || "No detailed backend message available."}
                                  </div>
                                  <div className="text-sm text-muted-foreground">
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
