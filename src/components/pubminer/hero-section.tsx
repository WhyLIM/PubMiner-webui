"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRight,
  Sparkles,
  Database,
  RefreshCw,
  ShieldCheck,
  FileOutput,
} from "lucide-react";
import Link from "next/link";

const heroSignals = [
  { label: "PMC-first OA retrieval", icon: ShieldCheck },
  { label: "Persistent task tracking", icon: Database },
  { label: "Chunk-based retries", icon: RefreshCw },
  { label: "CSV export for downstream analysis", icon: FileOutput },
];

export function HeroSection() {
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-primary/3 via-transparent to-transparent" />
      <div className="pointer-events-none absolute left-10 top-20 h-64 w-64 rounded-full bg-primary/5 blur-3xl" />
      <div className="pointer-events-none absolute bottom-10 right-10 h-96 w-96 rounded-full bg-primary/3 blur-3xl" />

      <div className="container py-20 md:py-28">
        <div className="mx-auto max-w-4xl text-center">
          <Badge variant="secondary" className="mb-6 gap-2 px-4 py-1.5 text-sm font-normal">
            <Sparkles className="h-3.5 w-3.5" />
            AI-Powered Literature Mining
          </Badge>

          <h1 className="mb-6 text-balance font-serif text-4xl font-normal leading-tight tracking-tight md:text-5xl lg:text-6xl">
            Extract Insights from
            <br />
            <span className="text-primary">Medical Literature</span>
          </h1>

          <p className="mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl">
            PubMiner helps researchers search PubMed precisely, recover legal open-access content,
            and convert large article sets into structured evidence tables.
          </p>

          <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link href="#search">
              <Button size="lg" className="gap-2 px-8">
                Start Mining
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>

        <div className="mx-auto mt-18 grid max-w-4xl grid-cols-2 gap-8 md:grid-cols-4">
          {heroSignals.map((item) => (
            <div key={item.label} className="group text-center">
              <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform group-hover:scale-110">
                <item.icon className="h-5 w-5" />
              </div>
              <div className="font-serif text-base font-medium leading-7 text-foreground/85">{item.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
