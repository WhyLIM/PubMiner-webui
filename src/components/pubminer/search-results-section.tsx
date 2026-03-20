"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/lib/store";
import { downloadOAPdf, downloadOAPdfs, resolveOAPdf, searchPubMed, type OAPdfResolution } from "@/lib/api";
import {
  BarChart3,
  CalendarDays,
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Layers3,
  LibraryBig,
  Loader2,
  ShieldCheck,
  Square,
} from "lucide-react";
import { toast } from "sonner";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });
const PAGE_SIZE = 10;
const PILL_BASE_CLASS =
  "inline-flex max-w-full truncate rounded-full border px-3 py-1 text-xs font-medium tracking-wide shadow-sm";

export function SearchResultsSection() {
  const {
    searchResults,
    appendSearchResults,
    selectedSearchPmids,
    setSelectedSearchPmids,
    toggleSelectedSearchPmid,
    searchSession,
    setSearchSession,
    oaPdfByPmid,
    setOaPdfResolutions,
    unpaywallEmail,
  } = useAppStore();
  const autoResolveInFlight = useRef(false);

  const [fullTextOnly, setFullTextOnly] = useState(false);
  const [yearFilter, setYearFilter] = useState("all");
  const [journalFilter, setJournalFilter] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedPmids, setExpandedPmids] = useState<string[]>([]);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isResolvingOaPdf, setIsResolvingOaPdf] = useState(false);
  const [oaPdfProgress, setOaPdfProgress] = useState<number | null>(null);
  const [oaPdfResolvedCount, setOaPdfResolvedCount] = useState(0);
  const [downloadingPmid, setDownloadingPmid] = useState<string | null>(null);
  const [isBatchDownloadingOaPdf, setIsBatchDownloadingOaPdf] = useState(false);

  const filteredResults = useMemo(() => {
    return searchResults.filter((item) => {
      if (fullTextOnly && !item.hasFullText) return false;
      if (yearFilter !== "all" && (item.year || "Unknown") !== yearFilter) return false;
      if (journalFilter !== "all" && (item.journal || "Unknown Journal") !== journalFilter) return false;
      return true;
    });
  }, [fullTextOnly, journalFilter, searchResults, yearFilter]);

  const totalPages = Math.max(Math.ceil(filteredResults.length / PAGE_SIZE), 1);
  const visiblePage = Math.min(currentPage, totalPages);
  const paginatedResults = useMemo(
    () => filteredResults.slice((visiblePage - 1) * PAGE_SIZE, visiblePage * PAGE_SIZE),
    [filteredResults, visiblePage]
  );

  const yearBuckets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of filteredResults) {
      const year = item.year || "Unknown";
      counts.set(year, (counts.get(year) || 0) + 1);
    }

    return Array.from(counts.entries())
      .sort(([a], [b]) => {
        if (a === "Unknown") return 1;
        if (b === "Unknown") return -1;
        return Number(a) - Number(b);
      })
      .map(([year, count]) => ({ year, count }));
  }, [filteredResults]);

  const journalBuckets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of filteredResults) {
      const journal = item.journal || "Unknown Journal";
      counts.set(journal, (counts.get(journal) || 0) + 1);
    }

    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [filteredResults]);

  const fullTextCount = useMemo(
    () => filteredResults.filter((item) => item.hasFullText).length,
    [filteredResults]
  );

  const yearOptions = useMemo(
    () =>
      Array.from(new Set(searchResults.map((item) => item.year || "Unknown"))).sort((a, b) => {
        if (a === "Unknown") return 1;
        if (b === "Unknown") return -1;
        return Number(a) - Number(b);
      }),
    [searchResults]
  );

  const journalOptions = useMemo(
    () =>
      Array.from(new Set(searchResults.map((item) => item.journal || "Unknown Journal"))).sort(),
    [searchResults]
  );

  const yearChartOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      grid: { left: 36, right: 12, top: 18, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: yearBuckets.map((item) => item.year),
        axisLine: { lineStyle: { color: "#d2dfd7" } },
        axisTick: { show: false },
        axisLabel: { color: "#4b5563", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#eef3ed" } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#4b5563", fontSize: 11 },
      },
      series: [
        {
          data: yearBuckets.map((item) => item.count),
          type: "bar",
          barWidth: "58%",
          itemStyle: {
            color: "#215c4f",
            borderRadius: [6, 6, 0, 0],
          },
        },
      ],
    }),
    [yearBuckets]
  );

  const availabilityChartOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      tooltip: { trigger: "item" },
      legend: {
        bottom: 0,
        textStyle: { color: "#4b5563", fontSize: 11 },
      },
      series: [
        {
          type: "pie",
          radius: ["54%", "74%"],
          center: ["50%", "44%"],
          label: { show: false },
          data: [
            { value: fullTextCount, name: "PMC Full Text", itemStyle: { color: "#215c4f" } },
            {
              value: Math.max(filteredResults.length - fullTextCount, 0),
              name: "Metadata Only",
              itemStyle: { color: "#d8e2db" },
            },
          ],
        },
      ],
    }),
    [filteredResults.length, fullTextCount]
  );

  const allResultsSelected =
    searchResults.length > 0 && selectedSearchPmids.length === searchResults.length;
  const unresolvedSearchArticles = useMemo(
    () =>
      searchResults.filter((item) => !oaPdfByPmid[item.pmid]).map((item) => ({
        pmid: item.pmid,
        doi: item.doi,
        pmcid: item.pmcid,
        title: item.title,
      })),
    [oaPdfByPmid, searchResults]
  );
  const selectedAvailableOaPmids = useMemo(
    () =>
      selectedSearchPmids.filter((pmid) => {
        const resolution = oaPdfByPmid[pmid];
        return resolution?.availability === "available" && Boolean(resolution.best_candidate?.pdf_url);
      }),
    [oaPdfByPmid, selectedSearchPmids]
  );
  const selectedBatchStats = useMemo(() => {
    let fastPmcCount = 0;
    let fallbackCount = 0;

    for (const pmid of selectedAvailableOaPmids) {
      const resolution = oaPdfByPmid[pmid];
      if (resolution?.best_candidate?.source === "pmc") {
        fastPmcCount += 1;
      } else {
        fallbackCount += 1;
      }
    }

    return {
      fastPmcCount,
      fallbackCount,
    };
  }, [oaPdfByPmid, selectedAvailableOaPmids]);

  const handleLoadMore = async () => {
    if (searchSession.source !== "query" || !searchSession.hasMore || isLoadingMore) {
      return;
    }

    try {
      setIsLoadingMore(true);
      const wereAllSelected =
        searchResults.length > 0 && selectedSearchPmids.length === searchResults.length;

      const response = await searchPubMed({
        query: searchSession.query,
        max_results: searchSession.pageSize,
        offset: searchSession.loadedCount,
      });

      appendSearchResults(response.results);
      setSearchSession({
        ...searchSession,
        totalAvailable: response.total_available,
        loadedCount: searchSession.loadedCount + response.results.length,
        hasMore: response.has_more,
      });

      if (wereAllSelected) {
        setSelectedSearchPmids([
          ...selectedSearchPmids,
          ...response.results.map((item) => item.pmid),
        ]);
      }

      toast.success(`Loaded ${response.results.length} more articles`);
    } catch (error) {
      console.error("Load more error:", error);
      toast.error("Failed to load more results");
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleResolveOaPdf = async () => {
    try {
      setIsResolvingOaPdf(true);
      setOaPdfProgress(0);
      setOaPdfResolvedCount(0);
      const articles = searchResults.map((item) => ({
        pmid: item.pmid,
        doi: item.doi,
        pmcid: item.pmcid,
        title: item.title,
      }));
      const results = await resolveOAPdf(articles, unpaywallEmail.trim() || undefined);
      setOaPdfResolutions(results);
      setOaPdfResolvedCount(results.length);
      setOaPdfProgress(100);

      const available = results.filter((item) => item.availability === "available").length;
      toast.success(`OA PDF check finished: ${available}/${results.length} available`);
    } catch (error) {
      console.error("Resolve OA PDF error:", error);
      toast.error("Failed to check OA PDF availability");
    } finally {
      setIsResolvingOaPdf(false);
      window.setTimeout(() => {
        setOaPdfProgress(null);
        setOaPdfResolvedCount(0);
      }, 500);
    }
  };

  useEffect(() => {
    if (searchResults.length === 0 || unresolvedSearchArticles.length === 0 || autoResolveInFlight.current) {
      return;
    }

    let cancelled = false;
    autoResolveInFlight.current = true;
    setIsResolvingOaPdf(true);
    setOaPdfProgress(0);
    setOaPdfResolvedCount(searchResults.length - unresolvedSearchArticles.length);

    void (async () => {
      try {
        const results = await resolveOAPdf(unresolvedSearchArticles, unpaywallEmail.trim() || undefined);
        if (cancelled) {
          return;
        }
        setOaPdfResolutions(results);
        setOaPdfResolvedCount(searchResults.length);
        setOaPdfProgress(100);
      } catch (error) {
        if (!cancelled) {
          console.error("Auto resolve OA PDF error:", error);
          toast.error("Automatic OA PDF check failed. You can retry manually.");
        }
      } finally {
        autoResolveInFlight.current = false;
        if (!cancelled) {
          setIsResolvingOaPdf(false);
          window.setTimeout(() => {
            setOaPdfProgress(null);
            setOaPdfResolvedCount(0);
          }, 500);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [searchResults, unresolvedSearchArticles, setOaPdfResolutions, unpaywallEmail]);

  const handleDownloadOaPdf = async (pmid: string) => {
    const item = searchResults.find((entry) => entry.pmid === pmid);
    if (!item) return;

    try {
      setDownloadingPmid(pmid);
      const download = await downloadOAPdf({
        pmid: item.pmid,
        doi: item.doi,
        pmcid: item.pmcid,
        title: item.title,
      }, unpaywallEmail.trim() || undefined);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = download.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast.success("OA PDF download started");
    } catch (error) {
      console.error("Download OA PDF error:", error);
      toast.error("Failed to download OA PDF");
    } finally {
      setDownloadingPmid(null);
    }
  };

  const handleBatchDownloadOaPdf = async () => {
    if (selectedAvailableOaPmids.length === 0) return;

    try {
      setIsBatchDownloadingOaPdf(true);
      const articles = searchResults
        .filter((item) => selectedAvailableOaPmids.includes(item.pmid))
        .map((item) => ({
          pmid: item.pmid,
          doi: item.doi,
          pmcid: item.pmcid,
          title: item.title,
        }));
      const download = await downloadOAPdfs(articles, unpaywallEmail.trim() || undefined);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = download.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast.success(`Packed ${selectedAvailableOaPmids.length} OA PDFs for download`);
    } catch (error) {
      console.error("Batch OA PDF download error:", error);
      toast.error("Batch OA PDF download failed");
    } finally {
      setIsBatchDownloadingOaPdf(false);
    }
  };

  if (searchResults.length === 0) {
    return null;
  }

  return (
    <section id="search-results" className="py-16">
      <div className="container">
        <div className="flex items-end justify-between gap-4 mb-8">
          <div>
            <h2 className="font-serif text-3xl md:text-4xl font-normal mb-2">
              Search Results
            </h2>
            <p className="text-muted-foreground">
              Review the articles first, then continue to the extraction setup below.
            </p>
          </div>
          <Badge variant="outline" className="font-normal">
            {selectedSearchPmids.length}/{searchResults.length} selected
          </Badge>
        </div>

        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-6">
            <Card className="gap-2 border-border/50">
              <CardHeader className="pb-1">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Layers3 className="w-4 h-4" />
                  Filters
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-1">
                <div className="flex items-center justify-between rounded-lg bg-muted/35 px-3 py-2">
                  <div>
                    <div className="text-sm font-medium">Only PMC full text</div>
                    <div className="text-xs text-muted-foreground">Useful before extraction</div>
                  </div>
                  <Switch
                    checked={fullTextOnly}
                    onCheckedChange={(checked) => {
                      setFullTextOnly(checked);
                      setCurrentPage(1);
                    }}
                  />
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Year</div>
                  <Select
                    value={yearFilter}
                    onValueChange={(value) => {
                      setYearFilter(value);
                      setCurrentPage(1);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-popover">
                      <SelectItem value="all">All years</SelectItem>
                      {yearOptions.map((year) => (
                        <SelectItem key={year} value={year}>
                          {year}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Journal</div>
                  <Select
                    value={journalFilter}
                    onValueChange={(value) => {
                      setJournalFilter(value);
                      setCurrentPage(1);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-popover">
                      <SelectItem value="all">All journals</SelectItem>
                      {journalOptions.map((journal) => (
                        <SelectItem key={journal} value={journal}>
                          {journal}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            <Card className="gap-2 border-border/50">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <BarChart3 className="w-4 h-4" />
                  Results by Year
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReactECharts option={yearChartOption} style={{ height: 220 }} notMerge lazyUpdate />
              </CardContent>
            </Card>

            <Card className="gap-2 border-border/50">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <LibraryBig className="w-4 h-4" />
                  Availability
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReactECharts option={availabilityChartOption} style={{ height: 220 }} notMerge lazyUpdate />
              </CardContent>
            </Card>

            <Card className="gap-2 border-border/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Top Journals</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {journalBuckets.map(([journal, count]) => (
                  <div key={journal} className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-muted-foreground">{journal}</span>
                    <Badge variant="secondary" className="font-normal">
                      {count}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="min-w-0 overflow-hidden border-border/50">
            <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="space-y-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Article List
                </CardTitle>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>{filteredResults.length} visible results</span>
                  <span>{fullTextCount} with PMC full text</span>
                  <span>Page {visiblePage} of {totalPages}</span>
                  {searchSession.source === "query" && (
                    <span>{searchResults.length}/{searchSession.totalAvailable} loaded</span>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={handleResolveOaPdf}
                  disabled={isResolvingOaPdf}
                >
                  {isResolvingOaPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                  Check OA PDF
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={handleBatchDownloadOaPdf}
                  disabled={isBatchDownloadingOaPdf || selectedAvailableOaPmids.length === 0}
                >
                  {isBatchDownloadingOaPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Batch Download OA PDF ({selectedAvailableOaPmids.length})
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() =>
                    setSelectedSearchPmids(allResultsSelected ? [] : searchResults.map((item) => item.pmid))
                  }
                >
                  {allResultsSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                  Select All
                </Button>
              </div>
              <div className="text-xs text-muted-foreground">
                {Object.keys(oaPdfByPmid).length === 0
                  ? "OA PDF availability now starts automatically after search results appear. Batch download is fastest when PMC can serve the PDF directly."
                  : selectedAvailableOaPmids.length === 0
                    ? "No checked OA PDF items are currently selected."
                    : selectedBatchStats.fallbackCount === 0
                      ? `Selected batch uses the PMC fast path for all ${selectedBatchStats.fastPmcCount} article(s).`
                      : `Selected batch: ${selectedBatchStats.fastPmcCount} PMC fast-path article(s), ${selectedBatchStats.fallbackCount} article(s) may fall back to slower external OA hosts.`}
              </div>
            </CardHeader>

            <CardContent className="min-w-0 overflow-hidden space-y-4">
              {oaPdfProgress !== null && (
                <div className="rounded-xl border border-amber-200/70 bg-amber-50/50 p-3">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium text-amber-900">Checking legal OA PDF availability</span>
                    <span className="text-amber-800">
                      {oaPdfResolvedCount}/{searchResults.length} checked
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-amber-800/80">
                    Results are shown first, then the backend fills OA PDF availability in the background for unresolved articles.
                  </div>
                </div>
              )}

              <div className="space-y-4">
                {paginatedResults.map((item) => {
                  const checked = selectedSearchPmids.includes(item.pmid);
                  const isExpanded = expandedPmids.includes(item.pmid);
                  const oaPdf = oaPdfByPmid[item.pmid];
                  const canDownloadOa = oaPdf?.availability === "available" && Boolean(oaPdf.best_candidate?.pdf_url);

                  return (
                    <div
                      key={item.pmid}
                      className={`w-full overflow-hidden rounded-2xl border p-4 transition-colors ${
                        checked ? "border-primary/35 bg-primary/5" : "border-border/60 bg-background"
                      }`}
                    >
                      <div className="grid w-full grid-cols-[auto_minmax(0,1fr)] gap-3">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggleSelectedSearchPmid(item.pmid)}
                          className="mt-1"
                        />

                        <div className="min-w-0 w-full space-y-3">
                          <div className="space-y-2">
                            <div className="break-words text-lg leading-snug text-foreground">
                              {item.title || "Untitled article"}
                            </div>

                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span className="inline-flex items-center gap-1">
                                <CalendarDays className="w-3 h-3" />
                                {item.year || "Unknown year"}
                              </span>
                              <span>PMID: {item.pmid}</span>
                              {item.pmcid && <span>PMCID: {item.pmcid}</span>}
                              {item.doi && <span>DOI: {item.doi}</span>}
                            </div>

                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`${PILL_BASE_CLASS} border-emerald-200 bg-emerald-50 text-emerald-900`}>
                                {item.journal || "Unknown journal"}
                              </span>
                              <span
                                className={`${PILL_BASE_CLASS} ${
                                  item.hasFullText
                                    ? "border-cyan-200 bg-cyan-50 text-cyan-900"
                                    : "border-slate-200 bg-slate-50 text-slate-700"
                                }`}
                              >
                                {item.hasFullText ? "PMC Full Text" : "Metadata Only"}
                              </span>
                              {oaPdf && (
                                <span
                                  className={`${PILL_BASE_CLASS} ${
                                    canDownloadOa
                                      ? "border-amber-200 bg-amber-50 text-amber-900"
                                      : "border-slate-200 bg-slate-50 text-slate-700"
                                  }`}
                                >
                                  {canDownloadOa ? "OA PDF Available" : "No OA PDF"}
                                </span>
                              )}
                              {!oaPdf && (
                                <span className={`${PILL_BASE_CLASS} border-amber-200 bg-amber-50/70 text-amber-800`}>
                                  OA PDF Checking...
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="truncate text-sm text-muted-foreground">
                            {item.authors.length > 0 ? item.authors.join(", ") : "No authors available"}
                          </div>

                          {oaPdf && (
                            <div className="rounded-xl border border-amber-200/70 bg-amber-50/45 p-3 text-sm">
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <div className="space-y-1 text-amber-800/85">
                                  <div className="font-medium text-amber-950">Legal OA PDF</div>
                                  <div>{oaPdf.reason}</div>
                                  {oaPdf.best_candidate && (
                                    <div className="flex flex-wrap gap-3 text-xs">
                                      <span>Source: {oaPdf.best_candidate.source}</span>
                                      {oaPdf.best_candidate.host_type && <span>Host: {oaPdf.best_candidate.host_type}</span>}
                                      {oaPdf.best_candidate.license && <span>License: {oaPdf.best_candidate.license}</span>}
                                    </div>
                                  )}
                                </div>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="gap-2"
                                  disabled={!canDownloadOa || downloadingPmid === item.pmid}
                                  onClick={() => handleDownloadOaPdf(item.pmid)}
                                >
                                  {downloadingPmid === item.pmid ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <Download className="w-4 h-4" />
                                  )}
                                  Download OA PDF
                                </Button>
                              </div>
                            </div>
                          )}
                          {!oaPdf && (
                            <div className="rounded-xl border border-amber-200/60 bg-amber-50/35 p-3 text-sm text-amber-800/85">
                              Automatic OA PDF check is running for this article.
                            </div>
                          )}

                          {(item.firstAuthor || item.affiliation || item.publicationStatus) && (
                            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                              {item.firstAuthor && (
                                <span>First author: {item.firstAuthor}</span>
                              )}
                              {item.publicationStatus && (
                                <span>Status: {item.publicationStatus}</span>
                              )}
                              {item.affiliation && (
                                <span className="max-w-full truncate">
                                  Affiliation: {item.affiliation}
                                </span>
                              )}
                            </div>
                          )}

                          {item.abstract && (
                            <div className="space-y-2">
                              <button
                                type="button"
                                className="inline-flex items-center gap-2 text-sm text-muted-foreground"
                                onClick={() =>
                                  setExpandedPmids((current) =>
                                    current.includes(item.pmid)
                                      ? current.filter((pmid) => pmid !== item.pmid)
                                      : [...current, item.pmid]
                                  )
                                }
                              >
                                <ChevronRight
                                  className={`w-4 h-4 transition-transform ${
                                    isExpanded ? "rotate-90" : ""
                                  }`}
                                />
                                Abstract Preview
                              </button>
                              {isExpanded && (
                                <p className="text-sm leading-6 text-muted-foreground">
                                  {item.abstract}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between gap-3 border-t border-border/50 pt-4">
                <div className="text-sm text-muted-foreground">
                  Showing {(visiblePage - 1) * PAGE_SIZE + 1}-{Math.min(visiblePage * PAGE_SIZE, filteredResults.length)} of {filteredResults.length}
                </div>
                <div className="flex items-center gap-2">
                  {searchSession.source === "query" && searchSession.hasMore && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={handleLoadMore}
                      disabled={isLoadingMore}
                    >
                      {isLoadingMore ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                      Load More
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={visiblePage === 1}
                    onClick={() => setCurrentPage((page) => Math.max(page - 1, 1))}
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Prev
                  </Button>
                  <Badge variant="outline" className="font-normal">
                    {visiblePage}/{totalPages}
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={visiblePage === totalPages}
                    onClick={() => setCurrentPage((page) => Math.min(page + 1, totalPages))}
                  >
                    Next
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
