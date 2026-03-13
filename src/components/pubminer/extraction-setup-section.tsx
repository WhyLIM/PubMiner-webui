"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Download, Loader2, Plus, Sparkles, X } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { startExtraction } from "@/lib/api";
import { toast } from "sonner";

interface CustomField {
  id: string;
  name: string;
  description: string;
  type: string;
  enumValues?: string[];
}

const baseFields = [
  { name: "rationale", description: "Why the study matters and what problem it addresses." },
  { name: "framework", description: "Conceptual or theoretical framework guiding the study." },
  { name: "lit_gaps", description: "Research gaps identified in prior literature." },
  { name: "objectives", description: "Main study goals or research objectives." },
  { name: "hypotheses", description: "Explicit hypotheses or expected relationships." },
  { name: "sample_n", description: "Sample size or number of observations analyzed." },
  { name: "region", description: "Geographic or population region covered by the study." },
  { name: "conditions", description: "Disease, condition, or target population being studied." },
  { name: "data_source", description: "Primary data source, dataset, or recruitment source." },
  { name: "methods", description: "Study design, methods, and analysis approach." },
  { name: "iv", description: "Independent variable or exposure of interest." },
  { name: "dv", description: "Dependent variable or main outcome." },
  { name: "cv", description: "Control variables or covariates adjusted for." },
  { name: "findings", description: "Core empirical findings reported in the paper." },
  { name: "stats_conclusion", description: "Statistical conclusion and significance summary." },
  { name: "hyp_evidence", description: "Whether results support the stated hypotheses." },
  { name: "interpretation", description: "Authors' interpretation of the findings." },
  { name: "comparison", description: "How results compare with prior studies." },
  { name: "theory_value", description: "Contribution to theory or conceptual understanding." },
  { name: "practical_value", description: "Applied or practical implications of the work." },
  { name: "future_work", description: "Suggested next steps or future research directions." },
  { name: "data_limit", description: "Data-related limitations noted by the authors." },
  { name: "method_limit", description: "Methodological limitations or design weaknesses." },
  { name: "validity_limit", description: "Threats to internal, external, or construct validity." },
];

const defaultCustomFields: CustomField[] = [
  { id: "biomarker_name", name: "biomarker_name", description: "Name of the biomarker", type: "text" },
  { id: "biomarker_type", name: "biomarker_type", description: "Type: single/composite/panel", type: "enum", enumValues: ["Single", "Composite", "Panel", "Unknown"] },
  { id: "biomarker_category", name: "biomarker_category", description: "Molecular category", type: "enum", enumValues: ["Protein", "DNA", "RNA", "Metabolite", "Epigenetic", "Cellular", "Other"] },
];

export function ExtractionSetupSection() {
  const { searchResults, selectedSearchPmids, addTask, setShowTasks, setShowResults } = useAppStore();

  const [fetchCitations, setFetchCitations] = useState(false);
  const [customFields, setCustomFields] = useState<CustomField[]>([]);
  const [showExample, setShowExample] = useState(false);
  const [isAddFieldOpen, setIsAddFieldOpen] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [newField, setNewField] = useState<Partial<CustomField>>({
    type: "text",
    name: "",
    description: "",
    enumValues: [],
  });
  const [enumInput, setEnumInput] = useState("");

  if (searchResults.length === 0) {
    return null;
  }

  const addCustomField = () => {
    if (!newField.name?.trim()) return;

    setCustomFields((current) => [
      ...current,
      {
        id: Date.now().toString(),
        name: newField.name.trim(),
        description: newField.description || "",
        type: newField.type || "text",
        enumValues: newField.enumValues,
      },
    ]);
    setIsAddFieldOpen(false);
    setNewField({ type: "text", name: "", description: "", enumValues: [] });
    setEnumInput("");
  };

  const handleStartExtraction = async () => {
    try {
      setIsStarting(true);

      if (selectedSearchPmids.length === 0) {
        toast.error("Please select at least one article from the list first");
        return;
      }

      const extractionResponse = await startExtraction({
        pmids: selectedSearchPmids,
        custom_fields: customFields.length > 0 ? customFields : null,
        fetch_citations: fetchCitations,
      });

      addTask({
        id: extractionResponse.task_id,
        query: "Selected Articles",
        pmids: selectedSearchPmids,
        status: "pending",
        progress: 0,
        total: selectedSearchPmids.length,
        completed: 0,
        failed: 0,
        createdAt: new Date().toISOString(),
        message: "Task queued",
        fullTextReport: undefined,
        citationReport: undefined,
        articleReport: undefined,
      });

      setShowTasks(true);
      setShowResults(false);
      toast.success("Extraction task started");

      setTimeout(() => {
        document.getElementById("tasks")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    } catch (error) {
      console.error("Extraction error:", error);
      toast.error("Failed to start extraction. Please check your connection and try again.");
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <section id="extraction-setup" className="py-16 bg-muted/20">
      <div className="container mx-auto max-w-5xl px-4">
        <div className="text-center mb-10">
          <h2 className="font-serif text-3xl md:text-4xl font-normal mb-4">
            LLM Extraction Setup
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            After reviewing the article list, configure the extraction fields and launch the task.
          </p>
        </div>

        <Card className="border-border/50 shadow-sm">
          <CardHeader className="space-y-3">
            <CardTitle className="text-lg">Selected Scope</CardTitle>
            <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
              <Badge variant="outline" className="font-normal">
                {selectedSearchPmids.length}/{searchResults.length} selected
              </Badge>
              <span>Only selected articles will be sent for extraction.</span>
            </div>
          </CardHeader>

          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>LLM Model</Label>
                <Select defaultValue="glm-4-flash">
                  <SelectTrigger className="bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-popover">
                    <SelectItem value="glm-4-flash">GLM-4-Flash (Fast)</SelectItem>
                    <SelectItem value="glm-4">GLM-4 (Balanced)</SelectItem>
                    <SelectItem value="glm-4-plus">GLM-4-Plus (Best)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background px-4 py-3">
                <div>
                  <Label>Fetch Citation Information</Label>
                  <p className="text-xs text-muted-foreground">
                    Include citation counts and references before export
                  </p>
                </div>
                <Switch checked={fetchCitations} onCheckedChange={setFetchCitations} />
              </div>
            </div>

            <Separator />

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">Base Extraction Fields</h4>
                <Badge variant="secondary" className="font-normal">
                  {baseFields.length} fields
                </Badge>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/60 p-3">
                <ScrollArea className="h-56">
                  <div className="grid gap-3 md:grid-cols-2">
                    {baseFields.map((field) => (
                      <div
                        key={field.name}
                        className="rounded-lg border border-border/50 bg-background px-3 py-3"
                      >
                        <code className="text-xs font-medium">{field.name}</code>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          {field.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">Custom Extraction Fields</h4>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="font-normal">
                    {customFields.length} fields
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setCustomFields(showExample ? [] : defaultCustomFields);
                      setShowExample(!showExample);
                    }}
                  >
                    {showExample ? "Clear Example" : "Load Example"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => {
                      const blob = new Blob([JSON.stringify({ fields: customFields }, null, 2)], {
                        type: "application/json",
                      });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "custom_fields.json";
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="w-4 h-4" />
                    Export
                  </Button>
                  <Dialog open={isAddFieldOpen} onOpenChange={setIsAddFieldOpen}>
                    <DialogTrigger asChild>
                      <Button size="sm" className="gap-2">
                        <Plus className="w-4 h-4" />
                        Add Field
                      </Button>
                    </DialogTrigger>
                    <DialogContent className="sm:max-w-md">
                      <DialogHeader>
                        <DialogTitle>Add Custom Field</DialogTitle>
                        <DialogDescription>
                          Define a new extraction field for the LLM task.
                        </DialogDescription>
                      </DialogHeader>
                      <div className="space-y-4 py-4">
                        <div className="space-y-2">
                          <Label>Field Name</Label>
                          <Input
                            value={newField.name || ""}
                            onChange={(e) => setNewField({ ...newField, name: e.target.value })}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Description</Label>
                          <Input
                            value={newField.description || ""}
                            onChange={(e) => setNewField({ ...newField, description: e.target.value })}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Field Type</Label>
                          <Select
                            value={newField.type}
                            onValueChange={(value) =>
                              setNewField({
                                ...newField,
                                type: value,
                                enumValues: value === "enum" ? [] : undefined,
                              })
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-popover">
                              <SelectItem value="text">Text</SelectItem>
                              <SelectItem value="enum">Enum</SelectItem>
                              <SelectItem value="number">Number</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>

                        {newField.type === "enum" && (
                          <div className="space-y-2">
                            <Label>Enum Values</Label>
                            <div className="flex gap-2">
                              <Input
                                value={enumInput}
                                onChange={(e) => setEnumInput(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" && enumInput.trim()) {
                                    e.preventDefault();
                                    setNewField({
                                      ...newField,
                                      enumValues: [...(newField.enumValues || []), enumInput.trim()],
                                    });
                                    setEnumInput("");
                                  }
                                }}
                              />
                              <Button
                                type="button"
                                variant="secondary"
                                onClick={() => {
                                  if (!enumInput.trim()) return;
                                  setNewField({
                                    ...newField,
                                    enumValues: [...(newField.enumValues || []), enumInput.trim()],
                                  });
                                  setEnumInput("");
                                }}
                              >
                                Add
                              </Button>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {(newField.enumValues || []).map((value) => (
                                <Badge key={value} variant="secondary" className="gap-1 font-normal">
                                  {value}
                                  <X
                                    className="w-3 h-3 cursor-pointer"
                                    onClick={() =>
                                      setNewField({
                                        ...newField,
                                        enumValues: (newField.enumValues || []).filter((item) => item !== value),
                                      })
                                    }
                                  />
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                      <DialogFooter>
                        <Button variant="outline" onClick={() => setIsAddFieldOpen(false)}>
                          Cancel
                        </Button>
                        <Button onClick={addCustomField}>Add</Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </div>

              <div className="space-y-2">
                {customFields.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border/60 py-6 text-center text-sm text-muted-foreground">
                    No custom fields defined yet.
                  </div>
                ) : (
                  customFields.map((field) => (
                    <div
                      key={field.id}
                      className="flex items-center justify-between rounded-lg border border-border/50 bg-background/60 p-3"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <code className="text-sm">{field.name}</code>
                          <Badge variant="secondary" className="text-xs font-normal">
                            {field.type}
                          </Badge>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{field.description}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setCustomFields((current) => current.filter((item) => item.id !== field.id))}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border/50 pt-6">
              <div className="text-sm text-muted-foreground">
                The extraction task will run on <span className="font-medium text-foreground">{selectedSearchPmids.length}</span> selected articles.
              </div>
              <Button
                size="lg"
                className="gap-2 px-8"
                onClick={handleStartExtraction}
                disabled={isStarting || selectedSearchPmids.length === 0}
              >
                {isStarting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Start Extraction
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
