import Link from "next/link";
import { Separator } from "@/components/ui/separator";
import { BookOpen, Github, Mail, ExternalLink, Twitter } from "lucide-react";

const footerLinks = {
  product: [
    { name: "Features", href: "#features" },
    { name: "Documentation", href: "#" },
    { name: "API Reference", href: "#" },
    { name: "Changelog", href: "#" },
  ],
  resources: [
    { name: "PubMed", href: "https://pubmed.ncbi.nlm.nih.gov/", external: true },
    { name: "NCBI API", href: "https://www.ncbi.nlm.nih.gov/home/develop/api/", external: true },
    { name: "PMC Open Access", href: "https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/", external: true },
    { name: "BioC Format", href: "https://bioc.sourceforge.io/", external: true },
  ],
  about: [
    { name: "About", href: "#" },
    { name: "Contact", href: "#" },
    { name: "Privacy Policy", href: "#" },
    { name: "Terms of Use", href: "#" },
  ],
};

export function Footer() {
  return (
    <footer className="border-t border-border/40 bg-muted/10">
      <div className="container py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4 group">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center transition-transform group-hover:scale-105">
                <BookOpen className="w-4 h-4 text-primary-foreground" />
              </div>
              <span className="font-serif text-lg font-semibold">PubMiner</span>
            </Link>
            <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
              Intelligent medical literature mining powered by advanced AI technology. 
              Extract structured insights from PubMed with unprecedented efficiency.
            </p>
          </div>

          {/* Product Links */}
          <div>
            <h4 className="font-medium text-sm mb-4">Product</h4>
            <ul className="space-y-2.5">
              {footerLinks.product.map((link) => (
                <li key={link.name}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources Links */}
          <div>
            <h4 className="font-medium text-sm mb-4">Resources</h4>
            <ul className="space-y-2.5">
              {footerLinks.resources.map((link) => (
                <li key={link.name}>
                  <a
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1"
                  >
                    {link.name}
                    {link.external && <ExternalLink className="w-3 h-3" />}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* About Links */}
          <div>
            <h4 className="font-medium text-sm mb-4">About</h4>
            <ul className="space-y-2.5">
              {footerLinks.about.map((link) => (
                <li key={link.name}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {link.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <Separator className="my-8" />

        {/* Bottom bar */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} PubMiner. All rights reserved.
          </p>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <Github className="w-4 h-4" />
            </a>
            <a
              href="https://twitter.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <Twitter className="w-4 h-4" />
            </a>
            <a
              href="mailto:contact@pubminer.dev"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <Mail className="w-4 h-4" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
