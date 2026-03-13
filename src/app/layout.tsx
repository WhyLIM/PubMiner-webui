import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Cormorant_Garamond, Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

// Sans-serif for body text - clean and readable
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// Monospace for code
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Serif for headings - elegant academic feel
const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

// Alternative sans-serif
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PubMiner - Intelligent Medical Literature Mining",
  description: "A sophisticated tool for automated extraction and analysis of medical research literature from PubMed using advanced AI technology.",
  keywords: ["PubMed", "literature mining", "medical research", "AI extraction", "bioinformatics", "academic research"],
  authors: [{ name: "PubMiner Team" }],
  icons: {
    icon: "/favicon.ico",
  },
  openGraph: {
    title: "PubMiner",
    description: "Intelligent Medical Literature Mining",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${cormorant.variable} ${inter.variable} antialiased bg-background text-foreground font-sans`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
