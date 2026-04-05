import { Header } from "@/components/pubminer/header";
import { Footer } from "@/components/pubminer/footer";
import { HeroSection } from "@/components/pubminer/hero-section";
import { SearchSection } from "@/components/pubminer/search-section";
import { SearchResultsSection } from "@/components/pubminer/search-results-section";
import { ExtractionSetupSection } from "@/components/pubminer/extraction-setup-section";
import { WorkflowSection } from "@/components/pubminer/workflow-section";
import { TasksSection } from "@/components/pubminer/tasks-section";
import { ResultsSection } from "@/components/pubminer/results-section";

export default function Home() {
  const defaultUnpaywallEmail = process.env.UNPAYWALL_EMAIL || "";

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />

      <main className="flex-1">
        {/* Hero */}
        <HeroSection />

        {/* Workflow */}
        <WorkflowSection />

        {/* Search - now includes Extraction Fields in Advanced Options */}
        <SearchSection defaultUnpaywallEmail={defaultUnpaywallEmail} />

        {/* Search Results */}
        <SearchResultsSection />

        {/* Extraction Setup */}
        <ExtractionSetupSection />

        {/* Tasks */}
        <TasksSection />

        {/* Results */}
        <ResultsSection />
      </main>

      <Footer />
    </div>
  );
}
