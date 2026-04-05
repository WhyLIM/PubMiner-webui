"use client";

import { useEffect, useState } from "react";
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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
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
import { formatPubMedSearchTerm, PUBMED_FIELD_GROUPS, PUBMED_FIELD_MAP } from "@/lib/pubmed-fields";
import { toast } from "sonner";

const BOOLEAN_OPERATORS = ["AND", "OR", "NOT"];

interface SearchTerm {
  id: string;
  term: string;
  field: string;
  operator: string;
}

const exampleQueries = [
  {
    label: "Aging Biomarkers",
    query: "(aging[tiab] OR longevity[tiab]) AND (biomarker*[tiab] OR \"biological age\"[tiab]) AND humans[filter] AND english[la] AND 2020:2026[dp]",
  },
  {
    label: "COVID-19 Vaccine",
    query: "(\"COVID-19 Vaccines\"[mh] OR \"covid-19 vaccine\"[tiab]) AND (effectiveness[tiab] OR efficacy[tiab]) AND (cohort[tiab] OR \"clinical trial\"[pt]) AND 2021:2026[dp]",
  },
  {
    label: "Cancer Immunotherapy",
    query: "((\"Neoplasms\"[mh] AND immunotherapy[tiab]) OR \"immune checkpoint inhibitors\"[tiab]) AND (survival[tiab] OR response[tiab]) AND (trial[tiab] OR \"clinical trial\"[pt]) NOT review[pt]",
  },
];

const INITIAL_QUERY_LOAD_SIZE = 50;

interface SearchSectionProps {
  defaultUnpaywallEmail?: string;
}

export function SearchSection({ defaultUnpaywallEmail = "" }: SearchSectionProps) {
  const [searchTerms, setSearchTerms] = useState<SearchTerm[]>([
    { id: "1", term: "", field: "all", operator: "" },
  ]);
  const [pmidList, setPmidList] = useState("");
  const [maxResults, setMaxResults] = useState("10");
  const [isLoading, setIsLoading] = useState(false);

  const {
    searchResults,
    setSearchResults,
    setSelectedSearchPmids,
    searchSession,
    setSearchSession,
    clearSearchResults,
    unpaywallEmail,
    setUnpaywallEmail,
    clearOaPdfResolutions,
  } = useAppStore();

  useEffect(() => {
    if (!unpaywallEmail && defaultUnpaywallEmail) {
      setUnpaywallEmail(defaultUnpaywallEmail);
    }
  }, [defaultUnpaywallEmail, setUnpaywallEmail, unpaywallEmail]);

  const generatedQuery = searchTerms
    .map((st, index) => {
      if (!st.term.trim()) return "";
      const prefix = index > 0 && st.operator ? `${st.operator} ` : "";
      return `${prefix}${formatPubMedSearchTerm(st.term, st.field)}`;
    })
    .filter(Boolean)
    .join(" ");

  const addSearchTerm = () => {
    setSearchTerms((current) => [
      ...current,
      { id: Date.now().toString(), term: "", field: "all", operator: "AND" },
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
        clearOaPdfResolutions();
        setSearchResults(metadataResults);
        setSelectedSearchPmids(metadataResults.map((item) => item.pmid));
        setSearchSession({
          searchSessionId: null,
          source: "pmid",
          query: "",
          totalAvailable: metadataResults.length,
          sessionTotal: metadataResults.length,
          loadedCount: metadataResults.length,
          loadSize: metadataResults.length,
          hasMore: false,
        });
        toast.success(`Loaded ${metadataResults.length} articles`);
      } else if (generatedQuery) {
        const scopeLimit = maxResults === "all" ? 10000 : parseInt(maxResults, 10);
        const initialLoadSize = Math.min(scopeLimit, INITIAL_QUERY_LOAD_SIZE);
        const searchResponse = await searchPubMed({
          query: generatedQuery,
          max_results: scopeLimit,
          offset: 0,
          load_size: initialLoadSize,
        });

        clearOaPdfResolutions();
        setSearchResults(searchResponse.results);
        setSelectedSearchPmids(searchResponse.results.map((item) => item.pmid));
        setSearchSession({
          searchSessionId: searchResponse.search_session_id,
          source: "query",
          query: generatedQuery,
          totalAvailable: searchResponse.total_available,
          sessionTotal: searchResponse.session_total,
          loadedCount: searchResponse.results.length,
          loadSize: searchResponse.load_size,
          hasMore: searchResponse.has_more,
        });
        toast.success(
          `Loaded ${searchResponse.results.length} of ${searchResponse.session_total} articles in this search set`
        );
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
    <section id="search" className="bg-muted/20 py-20">
      <div className="container mx-auto max-w-5xl px-4">
        <div className="mb-12 text-center">
          <h2 className="mb-4 font-serif text-3xl font-normal md:text-4xl">
            Search Literature
          </h2>
          <p className="mx-auto max-w-2xl text-muted-foreground">
            Find the articles first. After you review the list below, configure LLM extraction separately.
          </p>
        </div>

        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-4">
            <Tabs defaultValue="query" className="w-full">
              <TabsList className="grid h-11 w-full grid-cols-2">
                <TabsTrigger value="query" className="gap-2">
                  <Search className="h-4 w-4" />
                  Query Builder
                </TabsTrigger>
                <TabsTrigger value="pmid" className="gap-2">
                  <FileText className="h-4 w-4" />
                  PMID List
                </TabsTrigger>
              </TabsList>

              <TabsContent value="query" className="mt-6 space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Search Term Builder</Label>
                    <Button variant="outline" size="sm" onClick={addSearchTerm} className="gap-1">
                      <Plus className="h-3 w-3" />
                      Add Condition
                    </Button>
                  </div>

                  {searchTerms.map((st, index) => {
                    const selectedField = PUBMED_FIELD_MAP[st.field] ?? PUBMED_FIELD_MAP.all;

                    return (
                      <div key={st.id} className="space-y-2 rounded-xl border border-border/50 bg-background/70 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {index > 0 && (
                            <Select
                              value={st.operator}
                              onValueChange={(value) => updateSearchTerm(st.id, { operator: value })}
                            >
                              <SelectTrigger className="h-10 w-20">
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
                            placeholder={`Enter search term, e.g. ${selectedField.example}`}
                            className="h-10 min-w-48 flex-1"
                            value={st.term}
                            onChange={(event) => updateSearchTerm(st.id, { term: event.target.value })}
                          />

                          <Select
                            value={st.field}
                            onValueChange={(value) => updateSearchTerm(st.id, { field: value })}
                          >
                            <SelectTrigger className="h-10 w-full min-w-[260px] max-w-[360px]">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="max-h-72 bg-popover">
                              {PUBMED_FIELD_GROUPS.map((group, groupIndex) => (
                                <SelectGroup key={group.label}>
                                  {groupIndex > 0 && <SelectSeparator />}
                                  <SelectLabel>{group.label}</SelectLabel>
                                  {group.fields.map((field) => (
                                    <SelectItem key={field.id} value={field.id}>
                                      {field.label}
                                    </SelectItem>
                                  ))}
                                </SelectGroup>
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
                              <X className="h-4 w-4" />
                            </Button>
                          )}
                        </div>

                        <div className="text-xs leading-5 text-muted-foreground">
                          {selectedField.description}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {generatedQuery && (
                  <div className="space-y-3 rounded-lg border border-border/50 bg-muted/50 p-4">
                    <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
                      <Wand2 className="h-4 w-4" />
                      Generated Query
                    </div>
                    <code className="break-all text-sm font-mono text-foreground">{generatedQuery}</code>
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
                          setSearchTerms([{ id: "1", term: item.query, field: "all", operator: "" }])
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
                      placeholder={"Enter one PMID per line:\n38723456\n38695432\n38654321"}
                      className="mt-2 min-h-32 bg-background font-mono text-sm"
                      value={pmidList}
                      onChange={(event) => setPmidList(event.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-4">
                    <Button variant="outline" size="sm" className="gap-2">
                      <Upload className="h-4 w-4" />
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
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 md:items-start">
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
                      ? searchSession.source === "query"
                        ? `Loaded ${searchSession.loadedCount} of ${searchSession.sessionTotal} articles in this search set (${searchSession.totalAvailable} matched in PubMed).`
                        : `Loaded ${searchResults.length} articles. Review them below before configuring extraction.`
                      : "Run a search to build the article list first."}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">OA PDF Settings</div>
                  <Input
                    type="email"
                    value={unpaywallEmail}
                    onChange={(event) => setUnpaywallEmail(event.target.value)}
                    placeholder="Unpaywall email (optional but recommended)"
                    className="max-w-sm bg-background"
                  />
                  <div className="text-sm text-muted-foreground">
                    Used when OA PDF detection needs DOI-based Unpaywall fallback. PMC-first checks still work without it.
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-center gap-3 pt-3 md:pt-4">
                <Button
                  size="lg"
                  className="gap-2 px-6"
                  onClick={handleSearchPreview}
                  disabled={isLoading || (!generatedQuery && !pmidList.trim())}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4" />
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
