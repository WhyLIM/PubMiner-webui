"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, Play, Sparkles, BookOpen, Database, Brain } from "lucide-react";
import Link from "next/link";

export function HeroSection() {
  return (
    <section className="relative overflow-hidden">
      {/* Subtle background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-primary/3 via-transparent to-transparent pointer-events-none" />
      
      {/* Decorative elements */}
      <div className="absolute top-20 left-10 w-64 h-64 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-96 h-96 bg-primary/3 rounded-full blur-3xl pointer-events-none" />
      
      <div className="container py-20 md:py-28">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <Badge variant="secondary" className="mb-6 px-4 py-1.5 text-sm font-normal gap-2">
            <Sparkles className="w-3.5 h-3.5" />
            AI-Powered Literature Mining
          </Badge>
          
          {/* Main heading */}
          <h1 className="font-serif text-4xl md:text-5xl lg:text-6xl font-normal leading-tight tracking-tight mb-6 text-balance">
            Extract Insights from
            <br />
            <span className="text-primary">Medical Literature</span>
          </h1>
          
          {/* Subtitle */}
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
            PubMiner automates the extraction of structured information from PubMed literature, 
            enabling researchers to analyze hundreds of articles with unprecedented efficiency.
          </p>
          
          {/* CTA buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="#search">
              <Button size="lg" className="gap-2 px-8">
                Start Mining
                <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
            <Button variant="outline" size="lg" className="gap-2 px-8">
              <Play className="w-4 h-4" />
              Watch Demo
            </Button>
          </div>
        </div>
        
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mt-20 max-w-4xl mx-auto">
          {[
            { value: "35M+", label: "PubMed Articles", icon: BookOpen },
            { value: "3M+", label: "PMC Full Text", icon: Database },
            { value: "24", label: "Extraction Fields", icon: Sparkles },
            { value: "10×", label: "Time Saved", icon: Brain },
          ].map((stat, index) => (
            <div key={index} className="text-center group">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary mb-3 transition-transform group-hover:scale-110">
                <stat.icon className="w-5 h-5" />
              </div>
              <div className="font-serif text-3xl md:text-4xl font-medium text-foreground mb-1">
                {stat.value}
              </div>
              <div className="text-sm text-muted-foreground">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
