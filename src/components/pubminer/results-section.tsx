"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ChevronDown,
  Download,
  FileSpreadsheet,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { downloadResults, getResultPreview, type ResultPreviewResponse } from "@/lib/api";
import { toast } from "sonner";

const COLUMN_LABELS: Record<string, string> = {
  pmid: "PMID",
  pmcid: "PMCID",
  doi: "DOI",
  title: "Title",
  authors: "Authors",
  first_author: "First Author",
  affiliation: "Affiliation",
  journal: "Journal",
  j_abbrev: "Journal Abbrev.",
  issn: "ISSN",
  journal_id: "Journal ID",
  pub_date: "Publication Date",
  year: "Year",
  volume: "Volume",
  issue: "Issue",
  pages: "Pages",
  article_type: "Article Type",
  publication_status: "Publication Status",
  language: "Language",
  status: "Record Status",
  last_revision: "Last Revision",
  has_fulltext: "Has Full Text",
  cited_count: "Cited Count",
  references_count: "References Count",
  grant_list: "Grant Support",
  abstract: "Abstract",
  keywords: "Keywords",
  mesh_terms: "MeSH Terms",
  rationale: "Rationale",
  framework: "Framework",
  lit_gaps: "Literature Gaps",
  objectives: "Objectives",
  hypotheses: "Hypotheses",
  sample_n: "Sample Size",
  region: "Region",
  conditions: "Conditions",
  data_source: "Data Source",
  methods: "Methods",
  iv: "Independent Variable",
  dv: "Dependent Variable",
  cv: "Control Variables",
  findings: "Findings",
  stats_concl: "Statistical Conclusion",
  hyp_evidence: "Hypothesis Evidence",
  interpretation: "Interpretation",
  vs_prior: "Comparison With Prior Work",
  theory_value: "Theory Value",
  practical_val: "Practical Value",
  future_work: "Future Work",
  data_limit: "Data Limitation",
  method_limit: "Method Limitation",
  validity: "Validity Limitation",
  error: "Error",
  raw_response: "Raw Response",
};

const IDENTIFIER_COLUMNS = ["pmid", "pmcid", "doi"];

const BIBLIOGRAPHIC_COLUMNS = [
  "title",
  "authors",
  "first_author",
  "affiliation",
  "journal",
  "j_abbrev",
  "issn",
  "journal_id",
  "pub_date",
  "year",
  "volume",
  "issue",
  "pages",
  "article_type",
  "publication_status",
  "language",
  "status",
  "last_revision",
  "has_fulltext",
  "cited_count",
  "references_count",
  "grant_list",
  "abstract",
  "keywords",
  "mesh_terms",
];

const EXTRACTION_COLUMNS = [
  "rationale",
  "framework",
  "lit_gaps",
  "objectives",
  "hypotheses",
  "sample_n",
  "region",
  "conditions",
  "data_source",
  "methods",
  "iv",
  "dv",
  "cv",
  "findings",
  "stats_concl",
  "hyp_evidence",
  "interpretation",
  "vs_prior",
  "theory_value",
  "practical_val",
  "future_work",
  "data_limit",
  "method_limit",
  "validity",
];

const DEFAULT_PREVIEW_COLUMNS = [
  "pmid",
  "pmcid",
  "doi",
  "title",
  "authors",
  "first_author",
  "journal",
  "article_type",
  "publication_status",
  "year",
  "rationale",
  "objectives",
  "methods",
  "findings",
];

const MODE_DEFAULT_COLUMNS: Record<"all" | "metadata" | "extraction", string[]> = {
  all: DEFAULT_PREVIEW_COLUMNS,
  metadata: [
    "pmid",
    "pmcid",
    "doi",
    "title",
    "authors",
    "first_author",
    "journal",
    "pub_date",
    "year",
    "article_type",
    "publication_status",
    "language",
    "abstract",
  ],
  extraction: [
    "pmid",
    "pmcid",
    "doi",
    "title",
    "rationale",
    "objectives",
    "methods",
    "findings",
    "future_work",
  ],
};

type ColumnGroup = {
  id: "identifiers" | "bibliographic" | "extraction" | "custom";
  label: string;
  columns: string[];
};

function getOrderedDefaults(
  mode: "all" | "metadata" | "extraction",
  availableColumns: string[]
) {
  const preferred = MODE_DEFAULT_COLUMNS[mode].filter((column) => availableColumns.includes(column));
  return preferred.length > 0 ? preferred : availableColumns.slice(0, 6);
}

function getColumnGroups(columns: string[]): ColumnGroup[] {
  const groups: ColumnGroup[] = [
    {
      id: "identifiers",
      label: "Identifiers",
      columns: columns.filter((column) => IDENTIFIER_COLUMNS.includes(column)),
    },
    {
      id: "bibliographic",
      label: "Bibliographic Info",
      columns: columns.filter((column) => BIBLIOGRAPHIC_COLUMNS.includes(column)),
    },
    {
      id: "extraction",
      label: "LLM Extraction",
      columns: columns.filter((column) => EXTRACTION_COLUMNS.includes(column)),
    },
  ];

  const assigned = new Set(groups.flatMap((group) => group.columns));
  const customColumns = columns.filter(
    (column) => !assigned.has(column) && !["error", "raw_response"].includes(column)
  );

  if (customColumns.length > 0) {
    groups.push({
      id: "custom",
      label: "Custom Fields",
      columns: customColumns,
    });
  }

  return groups.filter((group) => group.columns.length > 0);
}

function getColumnDisplayLabel(column: string) {
  return COLUMN_LABELS[column] || column.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function getColumnGroupId(column: string): ColumnGroup["id"] {
  if (IDENTIFIER_COLUMNS.includes(column)) return "identifiers";
  if (BIBLIOGRAPHIC_COLUMNS.includes(column)) return "bibliographic";
  if (EXTRACTION_COLUMNS.includes(column)) return "extraction";
  return "custom";
}

function getGroupStyles(groupId: ColumnGroup["id"]) {
  if (groupId === "identifiers") {
    return {
      card: "border-sky-200/70 bg-sky-50/50",
      title: "text-sky-800",
      meta: "text-sky-700/80",
      checkbox: "border-sky-300 data-[state=checked]:border-sky-600 data-[state=checked]:bg-sky-600",
      label: "text-sky-900",
      field: "text-sky-800",
      fieldMeta: "text-sky-700/75",
      header: "bg-sky-50/70",
    };
  }

  if (groupId === "bibliographic") {
    return {
      card: "border-teal-200/70 bg-teal-50/45",
      title: "text-teal-800",
      meta: "text-teal-700/80",
      checkbox: "border-teal-300 data-[state=checked]:border-teal-600 data-[state=checked]:bg-teal-600",
      label: "text-teal-900",
      field: "text-teal-900",
      fieldMeta: "text-teal-700/75",
      header: "bg-teal-50/60",
    };
  }

  if (groupId === "extraction") {
    return {
      card: "border-amber-200/70 bg-amber-50/45",
      title: "text-amber-900",
      meta: "text-amber-800/80",
      checkbox: "border-amber-300 data-[state=checked]:border-amber-600 data-[state=checked]:bg-amber-600",
      label: "text-amber-950",
      field: "text-amber-950",
      fieldMeta: "text-amber-800/75",
      header: "bg-amber-50/65",
    };
  }

  return {
    card: "border-slate-200/70 bg-slate-50/40",
    title: "text-slate-800",
    meta: "text-slate-600",
    checkbox: "border-slate-300 data-[state=checked]:border-slate-600 data-[state=checked]:bg-slate-600",
    label: "text-slate-900",
    field: "text-slate-900",
    fieldMeta: "text-slate-600/80",
    header: "bg-slate-50/60",
  };
}

function getGroupGridTemplate(groupId: ColumnGroup["id"], columnCount: number) {
  if (groupId === "identifiers") {
    return `repeat(auto-fit, minmax(${columnCount <= 3 ? 110 : 120}px, 1fr))`;
  }

  if (groupId === "custom") {
    return "repeat(auto-fit, minmax(180px, 1fr))";
  }

  return "repeat(auto-fit, minmax(160px, 1fr))";
}

export function ResultsSection() {
  const { tasks, showResults } = useAppStore();
  const [preview, setPreview] = useState<ResultPreviewResponse | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_PREVIEW_COLUMNS);
  const [previewMode, setPreviewMode] = useState<"all" | "metadata" | "extraction">("all");

  const latestResultTask = tasks.find(
    (t) => (t.status === "completed" || t.status === "partial") && t.resultFile
  );

  const loadPreview = async (
    filename: string,
    mode: "all" | "metadata" | "extraction" = previewMode
  ) => {
    try {
      setIsLoadingPreview(true);
      const data = await getResultPreview(filename, 20, mode);
      setPreview(data);
      setSelectedColumns(getOrderedDefaults(mode, data.columns));
    } catch (error) {
      console.error("Preview error:", error);
      toast.error("Failed to load result preview");
      setPreview(null);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  useEffect(() => {
    if (!showResults || !latestResultTask?.resultFile) return;
    loadPreview(latestResultTask.resultFile, previewMode);
  }, [showResults, latestResultTask?.resultFile, previewMode]);

  const visibleColumns = useMemo(() => {
    if (!preview) return [];
    return preview.columns.filter((column) => selectedColumns.includes(column));
  }, [preview, selectedColumns]);

  const columnGroups = useMemo(() => {
    if (!preview) return [];
    return getColumnGroups(preview.columns);
  }, [preview]);

  const primaryColumnGroups = useMemo(
    () => columnGroups.filter((group) => group.id !== "custom"),
    [columnGroups]
  );
  const customColumnGroup = useMemo(
    () => columnGroups.find((group) => group.id === "custom"),
    [columnGroups]
  );

  const articleReport = latestResultTask?.articleReport || [];
  const articleSummary = useMemo(() => {
    return {
      fullTable: articleReport.filter((item) => item.result_status === "full_table").length,
      metadataOnly: articleReport.filter((item) => item.result_status === "metadata_only").length,
      noPmc: articleReport.filter((item) => item.fulltext_status === "no_pmc").length,
      extractionFailed: articleReport.filter((item) => item.extraction_status === "failed").length,
    };
  }, [articleReport]);

  if (!showResults || !latestResultTask) {
    return null;
  }

  const handleDownload = async (mode: "all" | "metadata" | "extraction") => {
    if (!latestResultTask.resultFile) return;

    try {
      const filename = latestResultTask.resultFile.split("/").pop() || latestResultTask.resultFile;
      const download = await downloadResults(filename, mode);

      const url = URL.createObjectURL(download.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = download.filename;
      a.click();
      URL.revokeObjectURL(url);

      toast.success("Download started!");
    } catch (error) {
      console.error("Download error:", error);
      toast.error("Failed to download results");
    }
  };

  const toggleColumn = (column: string) => {
    setSelectedColumns((current) => {
      if (current.includes(column)) {
        return current.length === 1 ? current : current.filter((item) => item !== column);
      }
      return [...current, column];
    });
  };

  const toggleGroup = (columns: string[], checked: boolean) => {
    setSelectedColumns((current) => {
      if (checked) {
        return Array.from(new Set([...current, ...columns]));
      }

      const next = current.filter((column) => !columns.includes(column));
      return next.length > 0 ? next : current;
    });
  };

  const handleSelectAllColumns = () => {
    if (!preview) return;
    setSelectedColumns(preview.columns);
  };

  const handleResetColumns = () => {
    if (!preview) return;
    setSelectedColumns(getOrderedDefaults(previewMode, preview.columns));
  };

  return (
    <section id="results" className="py-20 bg-muted/20">
      <div className="container">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="mb-2 font-serif text-3xl font-normal md:text-4xl">Extraction Results</h2>
            <p className="text-muted-foreground">
              Structured information extracted from {latestResultTask.total} articles
            </p>
          </div>
          <Badge variant="secondary" className="w-fit font-normal">
            {latestResultTask.completed} Extracted
          </Badge>
        </div>

        <Card className="border-border/50">
          <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileSpreadsheet className="h-5 w-5" />
              Extracted Data Preview
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              className="gap-2 self-start md:self-auto"
              onClick={() => latestResultTask.resultFile && loadPreview(latestResultTask.resultFile, previewMode)}
              disabled={isLoadingPreview}
            >
              {isLoadingPreview ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh Preview
            </Button>
          </CardHeader>

          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <Card>
                <CardContent className="pt-6">
                  <div className="text-2xl font-bold">{latestResultTask.total}</div>
                  <p className="text-sm text-muted-foreground">Total Articles</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="text-2xl font-bold text-emerald-600">{latestResultTask.completed}</div>
                  <p className="text-sm text-muted-foreground">Successfully Extracted</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="text-2xl font-bold text-red-600">{latestResultTask.failed}</div>
                  <p className="text-sm text-muted-foreground">Failed</p>
                </CardContent>
              </Card>
            </div>

            {articleReport.length > 0 && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="text-sm font-medium">Article Mapping</div>
                  <Badge variant="outline" className="font-normal">
                    {articleSummary.fullTable} in full table
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {articleSummary.metadataOnly} metadata only
                  </Badge>
                  {articleSummary.noPmc > 0 && (
                    <Badge variant="outline" className="font-normal">
                      {articleSummary.noPmc} no PMC
                    </Badge>
                  )}
                  {articleSummary.extractionFailed > 0 && (
                    <Badge variant="outline" className="font-normal">
                      {articleSummary.extractionFailed} extraction failed
                    </Badge>
                  )}
                </div>

                <ScrollArea className="h-[220px] rounded-md border border-border/50">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>PMID</TableHead>
                        <TableHead>Title</TableHead>
                        <TableHead>Full Text</TableHead>
                        <TableHead>Extraction</TableHead>
                        <TableHead>Result</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {articleReport.map((item) => (
                        <TableRow key={item.pmid}>
                          <TableCell>{item.pmid}</TableCell>
                          <TableCell className="max-w-[420px]">
                            <div className="truncate">{item.title}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="font-normal">
                              {item.fulltext_status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="font-normal">
                              {item.extraction_status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="font-normal">
                              {item.result_status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </div>
            )}

            {preview && (
              <div className="space-y-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <Tabs
                    value={previewMode}
                    onValueChange={(value) => setPreviewMode(value as "all" | "metadata" | "extraction")}
                  >
                    <TabsList className="grid h-9 w-full grid-cols-3 lg:w-[360px]">
                      <TabsTrigger value="metadata">Metadata View</TabsTrigger>
                      <TabsTrigger value="extraction">LLM View</TabsTrigger>
                      <TabsTrigger value="all">Full View</TabsTrigger>
                    </TabsList>
                  </Tabs>

                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={handleSelectAllColumns}>
                      Select All
                    </Button>
                    <Button variant="ghost" size="sm" onClick={handleResetColumns}>
                      Reset
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" className="gap-2">
                          <Download className="h-4 w-4" />
                          Download CSV
                          <ChevronDown className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="bg-popover">
                        <DropdownMenuItem onClick={() => handleDownload("metadata")}>Metadata Only</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownload("extraction")}>LLM Fields Only</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownload("all")}>Full Table</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-muted-foreground">
                    Showing {preview.preview_rows} rows of {preview.total_rows}
                  </div>
                  <div className="text-sm text-muted-foreground">{visibleColumns.length} columns visible</div>
                </div>

                <div className="space-y-4 rounded-xl border border-border/50 bg-background/70 p-4">
                  <div className="text-sm font-medium">Visible Columns</div>
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                      {primaryColumnGroups.map((group) => {
                        const checkedCount = group.columns.filter((column) => selectedColumns.includes(column)).length;
                        const allChecked = checkedCount === group.columns.length;
                        const styles = getGroupStyles(group.id);
                        const flexGrow = Math.max(group.columns.length, group.id === "identifiers" ? 3 : 6);
                        const minWidth = group.id === "identifiers" ? 180 : 300;

                        return (
                          <div
                            key={group.id}
                            className={`space-y-3 rounded-lg p-4 ${styles.card}`}
                            style={{ flexGrow, flexBasis: 0, minWidth }}
                          >
                            <label className="flex items-center justify-between gap-3">
                              <div>
                                <div className={`text-sm font-medium ${styles.title}`}>{group.label}</div>
                                <div className={`text-xs ${styles.meta}`}>
                                  {checkedCount}/{group.columns.length} selected
                                </div>
                              </div>
                              <Checkbox
                                checked={allChecked}
                                onCheckedChange={(checked) => toggleGroup(group.columns, Boolean(checked))}
                                className={styles.checkbox}
                              />
                            </label>
                            <div
                              className="grid gap-x-4 gap-y-2"
                              style={{ gridTemplateColumns: getGroupGridTemplate(group.id, group.columns.length) }}
                            >
                              {group.columns.map((column) => (
                                <label key={column} className={`flex items-start gap-2 text-sm ${styles.label}`}>
                                  <Checkbox
                                    checked={selectedColumns.includes(column)}
                                    onCheckedChange={() => toggleColumn(column)}
                                    className={`mt-0.5 ${styles.checkbox}`}
                                  />
                                  <span className="min-w-0 leading-4">
                                    <span className={`block ${styles.field}`}>{getColumnDisplayLabel(column)}</span>
                                    <span className={`block text-xs ${styles.fieldMeta}`}>{column}</span>
                                  </span>
                                </label>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {customColumnGroup && (
                      <div className={`space-y-3 rounded-lg p-4 ${getGroupStyles("custom").card}`}>
                        <label className="flex items-center justify-between gap-3">
                          <div>
                            <div className={`text-sm font-medium ${getGroupStyles("custom").title}`}>
                              {customColumnGroup.label}
                            </div>
                            <div className={`text-xs ${getGroupStyles("custom").meta}`}>
                              {customColumnGroup.columns.filter((column) => selectedColumns.includes(column)).length}/
                              {customColumnGroup.columns.length} selected
                            </div>
                          </div>
                          <Checkbox
                            checked={customColumnGroup.columns.every((column) => selectedColumns.includes(column))}
                            onCheckedChange={(checked) =>
                              toggleGroup(customColumnGroup.columns, Boolean(checked))
                            }
                            className={getGroupStyles("custom").checkbox}
                          />
                        </label>
                        <div
                          className="grid gap-x-4 gap-y-2"
                          style={{
                            gridTemplateColumns: getGroupGridTemplate("custom", customColumnGroup.columns.length),
                          }}
                        >
                          {customColumnGroup.columns.map((column) => (
                            <label
                              key={column}
                              className={`flex items-start gap-2 text-sm ${getGroupStyles("custom").label}`}
                            >
                              <Checkbox
                                checked={selectedColumns.includes(column)}
                                onCheckedChange={() => toggleColumn(column)}
                                className={`mt-0.5 ${getGroupStyles("custom").checkbox}`}
                              />
                              <span className="min-w-0 leading-4">
                                <span className={`block ${getGroupStyles("custom").field}`}>
                                  {getColumnDisplayLabel(column)}
                                </span>
                                <span className={`block text-xs ${getGroupStyles("custom").fieldMeta}`}>
                                  {column}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto rounded-md border border-border/50">
              <ScrollArea className="h-[460px] w-full">
                {isLoadingPreview ? (
                  <div className="flex min-h-[320px] items-center justify-center text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading preview...
                    </div>
                  </div>
                ) : preview && visibleColumns.length > 0 ? (
                  <Table className="min-w-max">
                    <TableHeader>
                      <TableRow>
                        {visibleColumns.map((column) => {
                          const groupStyles = getGroupStyles(getColumnGroupId(column));
                          return (
                            <TableHead
                              key={column}
                              className={`min-w-[180px] border-b ${groupStyles.header}`}
                            >
                              <div className="leading-4">
                                <div className={`font-medium ${groupStyles.title}`}>
                                  {getColumnDisplayLabel(column)}
                                </div>
                                <div className={`text-xs font-normal ${groupStyles.meta}`}>{column}</div>
                              </div>
                            </TableHead>
                          );
                        })}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.rows.map((row, index) => (
                        <TableRow key={`${preview.filename}-${index}`}>
                          {visibleColumns.map((column) => (
                            <TableCell key={`${column}-${index}`} className="align-top">
                              <div className="max-w-[320px] whitespace-pre-wrap break-words text-sm">
                                {String(row[column] ?? "") || "-"}
                              </div>
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="flex min-h-[320px] items-center justify-center px-6 text-center text-muted-foreground">
                    Preview is not available yet. You can still download the CSV file directly.
                  </div>
                )}
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
