"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Brain,
  Download,
  FileOutput,
  Search,
} from "lucide-react";

const workflowSteps = [
  {
    icon: Search,
    title: "Search and stage the literature set",
    description:
      "Start with query-builder search, PMID upload, or curated article lists before pushing anything into extraction.",
    signals: ["Grouped PubMed fields", "Boolean logic", "PMID list support"],
    tone: "text-sky-700",
    surface: "bg-sky-50",
  },
  {
    icon: Download,
    title: "Resolve legal full text and OA PDF paths",
    description:
      "Use PMC-first retrieval and OA resolution so the pipeline favors legitimate, programmatic access routes.",
    signals: ["PMC-first retrieval", "OA PDF resolution", "Batch download fast path"],
    tone: "text-emerald-700",
    surface: "bg-emerald-50",
  },
  {
    icon: Brain,
    title: "Run chunked extraction with retries",
    description:
      "Process large batches with persistent task status, chunk tracking, retry controls, and cache-aware extraction.",
    signals: ["Persistent task store", "Chunk progress", "Retry failed articles"],
    tone: "text-violet-700",
    surface: "bg-violet-50",
  },
  {
    icon: FileOutput,
    title: "Export evidence in analysis-ready form",
    description:
      "Finish with structured outputs that are easier to review, subset, and bring into downstream statistics or screening work.",
    signals: ["CSV outputs", "Article-level status", "Structured fields"],
    tone: "text-amber-700",
    surface: "bg-amber-50",
  },
];

export function WorkflowSection() {
  return (
    <section id="workflow" className="bg-muted/10 py-20">
      <div className="container space-y-10">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-4 font-serif text-3xl font-normal md:text-4xl">
            Search, Extract, Export
          </h2>
          <p className="text-muted-foreground">
            Search the literature, resolve legal OA access, run chunked extraction, and export results in a review-friendly format.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {workflowSteps.map((step, index) => (
            <Card
              key={step.title}
              className="border-border/40 bg-background/95 shadow-sm transition-colors hover:bg-background"
            >
              <CardContent className="p-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className={`inline-flex h-12 w-12 items-center justify-center rounded-2xl ${step.surface}`}>
                    <step.icon className={`h-6 w-6 ${step.tone}`} />
                  </div>
                  <Badge variant="outline" className="font-normal">
                    Step {index + 1}
                  </Badge>
                </div>

                <div className="space-y-4">
                  <div>
                    <h3 className="mb-2 font-serif text-xl font-medium text-foreground">
                      {step.title}
                    </h3>
                    <p className="text-sm leading-6 text-muted-foreground">{step.description}</p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {step.signals.map((signal) => (
                      <Badge key={signal} variant="secondary" className="font-normal">
                        {signal}
                      </Badge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
