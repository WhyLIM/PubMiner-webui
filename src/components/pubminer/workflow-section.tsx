"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Search,
  Download,
  Brain,
  FileOutput,
  ArrowRight,
  Database,
  Sparkles,
  Layers,
  RefreshCw,
  Zap,
  Shield,
} from "lucide-react";

const steps = [
  {
    icon: Search,
    title: "Search PubMed",
    description:
      "Enter your research query using advanced search fields or upload a list of PMIDs.",
    color: "text-blue-600",
    bgColor: "bg-blue-50",
    features: ["30+ field types", "Boolean operators", "Date filters"],
  },
  {
    icon: Download,
    title: "Fetch Full Text",
    description:
      "Retrieve full-text articles from PMC Open Access Subset with intelligent section filtering.",
    color: "text-emerald-600",
    bgColor: "bg-emerald-50",
    features: ["Auto retrieval", "Section parsing", "Open access"],
  },
  {
    icon: Brain,
    title: "AI Extraction",
    description:
      "Large Language Models analyze each article and extract structured information based on your schema.",
    color: "text-violet-600",
    bgColor: "bg-violet-50",
    features: ["GLM-4 models", "High accuracy", "Custom schemas"],
  },
  {
    icon: FileOutput,
    title: "Export Results",
    description:
      "Download your results as a clean CSV file, ready for statistical analysis or integration.",
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    features: ["CSV/JSON export", "Standardized fields", "Ready for analysis"],
  },
];

const highlights = [
  {
    icon: Zap,
    title: "Lightning Fast",
    description: "Process hundreds of articles in minutes with optimized API calls",
  },
  {
    icon: Shield,
    title: "Reliable & Secure",
    description: "Automatic retry, checkpoint system, and secure API handling",
  },
  {
    icon: Layers,
    title: "Fully Customizable",
    description: "Define custom extraction fields for your specific research domain",
  },
  {
    icon: RefreshCw,
    title: "Resume Anytime",
    description: "Pause and resume long-running tasks without data loss",
  },
];

export function WorkflowSection() {
  return (
    <section id="workflow" className="py-20 bg-muted/10">
      <div className="container">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="font-serif text-3xl md:text-4xl font-normal mb-4">
            How It Works
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            From raw literature to structured data in four seamless steps, powered by AI.
          </p>
        </div>

        {/* Workflow steps */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 relative mb-20">
          {/* Connection lines (desktop) */}
          <div className="hidden lg:block absolute top-16 left-[12.5%] right-[12.5%] h-0.5 bg-border/50" />

          {steps.map((step, index) => (
            <div key={index} className="relative">
              {/* Step card */}
              <Card className="border-border/40 bg-background hover:shadow-lg transition-all duration-300 h-full group">
                <CardContent className="p-6">
                  {/* Step number */}
                  <div className="flex items-center gap-3 mb-4">
                    <div
                      className={`w-12 h-12 rounded-xl ${step.bgColor} flex items-center justify-center group-hover:scale-110 transition-transform`}
                    >
                      <step.icon className={`w-6 h-6 ${step.color}`} />
                    </div>
                    <Badge variant="outline" className="font-normal">
                      Step {index + 1}
                    </Badge>
                  </div>

                  {/* Content */}
                  <h3 className="font-serif text-xl font-medium mb-2">
                    {step.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed mb-4">
                    {step.description}
                  </p>

                  {/* Features */}
                  <div className="flex flex-wrap gap-2">
                    {step.features.map((feature, i) => (
                      <Badge key={i} variant="secondary" className="text-xs font-normal">
                        {feature}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Arrow (mobile) */}
              {index < steps.length - 1 && (
                <div className="lg:hidden flex justify-center my-4">
                  <ArrowRight className="w-5 h-5 text-muted-foreground rotate-90" />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Highlights */}
        <div className="border-t border-border/50 pt-16">
          <div className="text-center mb-12">
            <h3 className="font-serif text-2xl font-normal mb-2">
              Why Choose PubMiner?
            </h3>
            <p className="text-sm text-muted-foreground">
              Built for researchers who need efficiency and reliability
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {highlights.map((highlight, index) => (
              <div
                key={index}
                className="flex items-start gap-4 p-4 rounded-lg hover:bg-muted/30 transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <highlight.icon className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h4 className="font-medium mb-1">{highlight.title}</h4>
                  <p className="text-sm text-muted-foreground">
                    {highlight.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
