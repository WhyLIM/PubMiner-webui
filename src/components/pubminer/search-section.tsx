"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Search,
  Upload,
  FileText,
  Plus,
  X,
  Wand2,
  Loader2,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { fetchMetadata, searchPubMed } from "@/lib/api";
import { toast } from "sonner";

const PUBMED_FIELDS: Record<string, { name: string; description: string; example: string }> = {
  "All Fields": {
    name: "全部字段",
    description: "Search all available fields",
    example: "cancer therapy",
  },
  "Title": {
    name: "标题",
    description: "Search article titles only",
    example: "biomarkers[Title]",
  },
  "Title/Abstract": {
    name: "标题/摘要",
    description: "Search titles and abstracts",
    example: "aging[Title/Abstract]",
  },
  "Abstract": {
    name: "摘要",
    description: "Search abstract content only",
    example: "efficacy[Abstract]",
  },
  "MeSH Terms": {
    name: "MeSH 主题词",
    description: "Medical Subject Headings",
    example: "neoplasms[MeSH]",
  },
  "Author": {
    name: "作者",
    description: "Search author names",
    example: "Smith J[Author]",
  },
  "Journal": {
    name: "期刊",
    description: "Search journal names",
    example: "Nature[Journal]",
  },
  "Date - Publication": {
    name: "发表日期",
    description: "Search publication dates",
    example: "2020:2024[pdat]",
  },
};

const BOOLEAN_OPERATORS = ["AND", "OR", "NOT"];

interface SearchTerm {
  id: string;
  term: string;
  field: string;
  operator: string;
}

const exampleQueries = [
  { label: "Aging Biomarkers", query: "aging biomarkers[Title/Abstract] AND humans[Filter]" },
  { label: "COVID-19 Vaccine", query: "COVID-19 vaccine[Title] AND efficacy[Title/Abstract]" },
  { label: "Cancer Immunotherapy", query: "cancer immunotherapy[MeSH] AND clinical trial[ptyp]" },
];

export function SearchSection() {
  const [searchTerms, setSearchTerms] = useState<SearchTerm[]>([
    { id: "1", term: "", field: "All Fields", operator: "" },
  ]);
  const [pmidList, setPmidList] = useState("");
  const [maxResults, setMaxResults] = useState("10");
  const [isLoading, setIsLoading] = useState(false);

  const {
    searchResults,
    setSearchResults,
    setSelectedSearchPmids,
    setSearchSession,
    clearSearchResults,
  } = useAppStore();

  const generatedQuery = searchTerms
    .map((st, index) => {
      if (!st.term.trim()) return "";
      const fieldSuffix = st.field === "All Fields" ? "" : `[${st.field}]`;
      const prefix = index > 0 && st.operator ? `${st.operator} ` : "";
      return `${prefix}${st.term}${fieldSuffix}`;
    })
    .filter(Boolean)
    .join(" ");

  const addSearchTerm = () => {
    setSearchTerms((current) => [
      ...current,
      { id: Date.now().toString(), term: "", field: "All Fields", operator: "AND" },
    ]);
  };

  const removeSearchTerm = (id: string) => {
    if (searchTerms.length === 1) return;
    setSearchTerms((current) => current.filter((item) => item.id !== id));
  };

  const updateSearchTerm = (id: string, updates: Partial<SearchTerm>) => {
    setSearchTerms((current) =>
      current.map((item) => (item.id === id ? { ...item, ...updates } : item))
    );
  };

  const handleSearchPreview = async () => {
    try {
      setIsLoading(true);

      if (pmidList.trim()) {
        const pmids = Array.from(new Set(pmidList.split("\n").map((p) => p.trim()).filter(Boolean)));
        if (pmids.length === 0) {
          toast.error("Please enter valid PMIDs");
          return;
        }

        const metadataResults = await fetchMetadata(pmids);
        setSearchResults(metadataResults);
        setSelectedSearchPmids(metadataResults.map((item) => item.pmid));
        setSearchSession({
          source: "pmid",
          query: "",
          totalAvailable: metadataResults.length,
          loadedCount: metadataResults.length,
          pageSize: metadataResults.length,
          hasMore: false,
        });
        toast.success(`Loaded ${metadataResults.length} articles`);
      } else if (generatedQuery) {
        const pageSize = maxResults === "all" ? 10000 : parseInt(maxResults, 10);
        const searchResponse = await searchPubMed({
          query: generatedQuery,
          max_results: pageSize,
          offset: 0,
        });

        setSearchResults(searchResponse.results);
        setSelectedSearchPmids(searchResponse.results.map((item) => item.pmid));
        setSearchSession({
          source: "query",
          query: generatedQuery,
          totalAvailable: searchResponse.total_available,
          loadedCount: searchResponse.results.length,
          pageSize,
          hasMore: searchResponse.has_more,
        });
        toast.success(`Found ${searchResponse.results.length} articles`);
      } else {
        toast.error("Please enter a search query or PMID list");
        return;
      }

      setTimeout(() => {
        document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    } catch (error) {
      console.error("Search preview error:", error);
      toast.error("Failed to load article results. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section id="search" className="py-20 bg-muted/20">
      <div className="container mx-auto max-w-5xl px-4">
        <div className="text-center mb-12">
          <h2 className="font-serif text-3xl md:text-4xl font-normal mb-4">
            Search Literature
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Find the articles first. After you review the list below, configure LLM extraction separately.
          </p>
        </div>

        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-4">
            <Tabs defaultValue="query" className="w-full">
              <TabsList className="grid w-full grid-cols-2 h-11">
                <TabsTrigger value="query" className="gap-2">
                  <Search className="w-4 h-4" />
                  Query Builder
                </TabsTrigger>
                <TabsTrigger value="pmid" className="gap-2">
                  <FileText className="w-4 h-4" />
                  PMID List
                </TabsTrigger>
              </TabsList>

              <TabsContent value="query" className="mt-6 space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Search Term Builder</Label>
                    <Button variant="outline" size="sm" onClick={addSearchTerm} className="gap-1">
                      <Plus className="w-3 h-3" />
                      Add Condition
                    </Button>
                  </div>

                  {searchTerms.map((st, index) => (
                    <div key={st.id} className="flex flex-wrap items-center gap-2">
                      {index > 0 && (
                        <Select
                          value={st.operator}
                          onValueChange={(value) => updateSearchTerm(st.id, { operator: value })}
                        >
                          <SelectTrigger className="w-20 h-10">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-popover">
                            {BOOLEAN_OPERATORS.map((op) => (
                              <SelectItem key={op} value={op}>
                                {op}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}

                      <Input
                        placeholder="Enter search term..."
                        className="flex-1 min-w-48 h-10"
                        value={st.term}
                        onChange={(e) => updateSearchTerm(st.id, { term: e.target.value })}
                      />

                      <Select
                        value={st.field}
                        onValueChange={(value) => updateSearchTerm(st.id, { field: value })}
                      >
                        <SelectTrigger className="w-44 h-10">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-popover max-h-64">
                          {Object.entries(PUBMED_FIELDS).map(([key, value]) => (
                            <SelectItem key={key} value={key}>
                              <span>{key}</span>
                              <span className="text-xs text-muted-foreground ml-2">({value.name})</span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>

                      {searchTerms.length > 1 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-10 w-10"
                          onClick={() => removeSearchTerm(st.id)}
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>

                {generatedQuery && (
                  <div className="p-4 rounded-lg bg-muted/50 border border-border/50">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                      <Wand2 className="w-4 h-4" />
                      Generated Query
                    </div>
                    <code className="text-sm font-mono text-foreground break-all">{generatedQuery}</code>
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Example Queries</Label>
                  <div className="flex flex-wrap gap-2">
                    {exampleQueries.map((item) => (
                      <Badge
                        key={item.label}
                        variant="secondary"
                        className="cursor-pointer font-normal"
                        onClick={() =>
                          setSearchTerms([{ id: "1", term: item.query, field: "All Fields", operator: "" }])
                        }
                      >
                        {item.label}
                      </Badge>
                    ))}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="pmid" className="mt-6">
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="pmids" className="text-sm font-medium">
                      PMID List
                    </Label>
                    <Textarea
                      id="pmids"
                      placeholder="Enter one PMID per line:&#10;38723456&#10;38695432&#10;38654321"
                      className="mt-2 min-h-32 font-mono text-sm bg-background"
                      value={pmidList}
                      onChange={(e) => setPmidList(e.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-4">
                    <Button variant="outline" size="sm" className="gap-2">
                      <Upload className="w-4 h-4" />
                      Upload File
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      {pmidList.split("\n").filter(Boolean).length} PMIDs
                    </span>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardHeader>

          <Separator />

          <CardContent className="pt-6">
            <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
              <div className="space-y-2">
                <div className="text-sm font-medium">Search Scope</div>
                <div className="max-w-xs">
                  <Select value={maxResults} onValueChange={setMaxResults}>
                    <SelectTrigger className="bg-background">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-popover">
                      <SelectItem value="10">10 articles</SelectItem>
                      <SelectItem value="50">50 articles</SelectItem>
                      <SelectItem value="100">100 articles</SelectItem>
                      <SelectItem value="200">200 articles</SelectItem>
                      <SelectItem value="500">500 articles</SelectItem>
                      <SelectItem value="all">All Results</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="text-sm text-muted-foreground">
                  {searchResults.length > 0
                    ? `Loaded ${searchResults.length} articles. Review them below before configuring extraction.`
                    : "Run a search to build the article list first."}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  size="lg"
                  className="gap-2 px-6"
                  onClick={handleSearchPreview}
                  disabled={isLoading || (!generatedQuery && !pmidList.trim())}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <Search className="w-4 h-4" />
                      {searchResults.length > 0 ? "Refresh Results" : "Search & Preview"}
                    </>
                  )}
                </Button>
                {searchResults.length > 0 && (
                  <Button variant="ghost" size="lg" onClick={clearSearchResults}>
                    Reset Results
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
