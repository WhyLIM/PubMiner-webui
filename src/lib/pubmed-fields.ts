export type PubMedFieldBehavior = "tag" | "raw" | "owner";

export interface PubMedFieldOption {
  id: string;
  label: string;
  tag?: string;
  behavior: PubMedFieldBehavior;
  group: string;
  description: string;
  example: string;
}

export const PUBMED_FIELDS: PubMedFieldOption[] = [
  { id: "all", label: "All Fields [all]", tag: "all", behavior: "tag", group: "Common", description: "Search all available PubMed fields.", example: "aging[all]" },
  { id: "tiab", label: "Title/Abstract [tiab]", tag: "tiab", behavior: "tag", group: "Common", description: "Search titles and abstracts.", example: "aging[tiab]" },
  { id: "ti", label: "Title [ti]", tag: "ti", behavior: "tag", group: "Common", description: "Search article titles.", example: "biomarkers[ti]" },
  { id: "tw", label: "Text Words [tw]", tag: "tw", behavior: "tag", group: "Common", description: "Search text words across title, abstract, keywords, and more.", example: "frailty[tw]" },
  { id: "mh", label: "MeSH Terms [mh]", tag: "mh", behavior: "tag", group: "Common", description: "Search MeSH terms.", example: "neoplasms[mh]" },
  { id: "majr", label: "MeSH Major Topic [majr]", tag: "majr", behavior: "tag", group: "Common", description: "Search MeSH major topic headings.", example: "aging[majr]" },
  { id: "filter", label: "Filter [filter] [sb]", tag: "filter", behavior: "tag", group: "Common", description: "Search PubMed filters such as free full text or humans.", example: "\"free full text\"[filter]" },
  { id: "pt", label: "Publication Type [pt]", tag: "pt", behavior: "tag", group: "Common", description: "Search publication types.", example: "\"clinical trial\"[pt]" },
  { id: "dp", label: "Publication Date [dp]", tag: "dp", behavior: "tag", group: "Common", description: "Search publication dates or ranges.", example: "2020:2025[dp]" },
  { id: "pmid", label: "PMID [pmid]", tag: "pmid", behavior: "tag", group: "Common", description: "Search PubMed identifiers.", example: "38723456[pmid]" },
  { id: "pmc-mid", label: "PMCID and MID", behavior: "raw", group: "Common", description: "Search PMCID or NIHMS identifiers directly, e.g. PMC2600426.", example: "PMC2600426" },

  { id: "au", label: "Author [au]", tag: "au", behavior: "tag", group: "People & Organizations", description: "Search author names.", example: "\"smith j\"[au]" },
  { id: "fau", label: "Full Author Name [fau]", tag: "fau", behavior: "tag", group: "People & Organizations", description: "Search full author names.", example: "\"smith john\"[fau]" },
  { id: "1au", label: "First Author Name [1au]", tag: "1au", behavior: "tag", group: "People & Organizations", description: "Search first author names.", example: "\"wang y\"[1au]" },
  { id: "lastau", label: "Last Author Name [lastau]", tag: "lastau", behavior: "tag", group: "People & Organizations", description: "Search last author names.", example: "\"zhang h\"[lastau]" },
  { id: "auid", label: "Author Identifier [auid]", tag: "auid", behavior: "tag", group: "People & Organizations", description: "Search author identifiers such as ORCID.", example: "\"0000-0002-1825-0097\"[auid]" },
  { id: "ad", label: "Affiliation [ad]", tag: "ad", behavior: "tag", group: "People & Organizations", description: "Search author affiliations.", example: "harvard[ad]" },
  { id: "cn", label: "Corporate Author [cn]", tag: "cn", behavior: "tag", group: "People & Organizations", description: "Search corporate authors.", example: "\"World Health Organization\"[cn]" },
  { id: "ed", label: "Editor [ed]", tag: "ed", behavior: "tag", group: "People & Organizations", description: "Search editors.", example: "\"brown t\"[ed]" },
  { id: "ir", label: "Investigator [ir]", tag: "ir", behavior: "tag", group: "People & Organizations", description: "Search investigator names.", example: "\"chen l\"[ir]" },
  { id: "fir", label: "Full Investigator Name [fir]", tag: "fir", behavior: "tag", group: "People & Organizations", description: "Search full investigator names.", example: "\"lee anna\"[fir]" },
  { id: "ps", label: "Personal Name as Subject [ps]", tag: "ps", behavior: "tag", group: "People & Organizations", description: "Search people who are the subject of the article.", example: "\"vamus h\"[ps]" },
  { id: "owner", label: "Owner", behavior: "owner", group: "People & Organizations", description: "Search citation owner acronyms using owner + acronym.", example: "ownernasa" },

  { id: "ta", label: "Journal [ta]", tag: "ta", behavior: "tag", group: "Publication & Source", description: "Search journal titles or abbreviations.", example: "nature[ta]" },
  { id: "book", label: "Book [book]", tag: "book", behavior: "tag", group: "Publication & Source", description: "Search book citations in PubMed.", example: "genereviews[book]" },
  { id: "isbn", label: "ISBN [isbn]", tag: "isbn", behavior: "tag", group: "Publication & Source", description: "Search ISBN values.", example: "\"9780306406157\"[isbn]" },
  { id: "ip", label: "Issue [ip]", tag: "ip", behavior: "tag", group: "Publication & Source", description: "Search journal issue numbers.", example: "3[ip]" },
  { id: "vi", label: "Volume [vi]", tag: "vi", behavior: "tag", group: "Publication & Source", description: "Search journal volume numbers.", example: "42[vi]" },
  { id: "pg", label: "Pagination [pg]", tag: "pg", behavior: "tag", group: "Publication & Source", description: "Search first page numbers.", example: "101[pg]" },
  { id: "la", label: "Language [la]", tag: "la", behavior: "tag", group: "Publication & Source", description: "Search article language.", example: "english[la]" },
  { id: "pl", label: "Place of Publication [pl]", tag: "pl", behavior: "tag", group: "Publication & Source", description: "Search the journal or book place of publication.", example: "england[pl]" },
  { id: "pubn", label: "Publisher [pubn]", tag: "pubn", behavior: "tag", group: "Publication & Source", description: "Search publisher names for books and documents.", example: "\"springer\"[pubn]" },
  { id: "tt", label: "Transliterated Title [tt]", tag: "tt", behavior: "tag", group: "Publication & Source", description: "Search transliterated titles.", example: "\"zhonghua yi xue za zhi\"[tt]" },
  { id: "jid", label: "NLM Unique ID [jid]", tag: "jid", behavior: "tag", group: "Publication & Source", description: "Search NLM journal unique IDs.", example: "\"0375267\"[jid]" },

  { id: "sh", label: "MeSH Subheadings [sh]", tag: "sh", behavior: "tag", group: "Topics & Indexing", description: "Search MeSH subheadings.", example: "therapy[sh]" },
  { id: "mhda", label: "MeSH Date [mhda]", tag: "mhda", behavior: "tag", group: "Topics & Indexing", description: "Search the date when MeSH terms were added.", example: "2024[mhda]" },
  { id: "nm", label: "Supplementary Concept [nm]", tag: "nm", behavior: "tag", group: "Topics & Indexing", description: "Search supplementary concept records.", example: "resveratrol[nm]" },
  { id: "ot", label: "Other Term [ot]", tag: "ot", behavior: "tag", group: "Topics & Indexing", description: "Search author keywords and other non-MeSH terms.", example: "geroscience[ot]" },
  { id: "pa", label: "Pharmacological Action [pa]", tag: "pa", behavior: "tag", group: "Topics & Indexing", description: "Search pharmacological action terms.", example: "anti-inflammatory[pa]" },
  { id: "cois", label: "Conflict of Interest Statement [cois]", tag: "cois", behavior: "tag", group: "Topics & Indexing", description: "Search conflict of interest statements.", example: "industry[cois]" },
  { id: "gr", label: "Grants and Funding [gr]", tag: "gr", behavior: "tag", group: "Topics & Indexing", description: "Search grant and funding information.", example: "\"R01AG012345\"[gr]" },
  { id: "rn", label: "EC/RN Number [rn]", tag: "rn", behavior: "tag", group: "Topics & Indexing", description: "Search EC or Registry Numbers.", example: "\"50-00-0\"[rn]" },
  { id: "comment-correction", label: "Comment Correction Type", behavior: "raw", group: "Topics & Indexing", description: "Search comment/correction tokens such as hascommentin or haserratumfor.", example: "hascommentin" },

  { id: "aid", label: "Article Identifier [aid]", tag: "aid", behavior: "tag", group: "Identifiers & Dates", description: "Search DOI, PII, and related article identifiers.", example: "10.1038/nature12373[aid]" },
  { id: "lid", label: "Location ID [lid]", tag: "lid", behavior: "tag", group: "Identifiers & Dates", description: "Search location IDs such as DOI values.", example: "\"10.1000/j.jmb.2025.01.001\"[lid]" },
  { id: "si", label: "Secondary Source ID [si]", tag: "si", behavior: "tag", group: "Identifiers & Dates", description: "Search secondary source identifiers.", example: "\"ClinicalTrials.gov/NCT01234567\"[si]" },
  { id: "sb", label: "Subset [sb]", tag: "sb", behavior: "tag", group: "Identifiers & Dates", description: "Search PubMed subsets such as systematic[sb] or publishers[sb].", example: "systematic[sb]" },
  { id: "crdt", label: "Create Date [crdt]", tag: "crdt", behavior: "tag", group: "Identifiers & Dates", description: "Search PubMed create dates.", example: "\"2025/01/01\"[crdt]" },
  { id: "edat", label: "Entry Date [edat]", tag: "edat", behavior: "tag", group: "Identifiers & Dates", description: "Search PubMed entry dates.", example: "\"2025/01/15\"[edat]" },
  { id: "dcom", label: "Completion Date [dcom]", tag: "dcom", behavior: "tag", group: "Identifiers & Dates", description: "Search NLM completion dates.", example: "2024[dcom]" },
  { id: "lr", label: "Modification Date [lr]", tag: "lr", behavior: "tag", group: "Identifiers & Dates", description: "Search record modification dates.", example: "\"2025/02/01\"[lr]" },
];

export const PUBMED_FIELD_MAP = Object.fromEntries(PUBMED_FIELDS.map((field) => [field.id, field]));
export const PUBMED_FIELD_GROUPS = Array.from(
  new Map(
    PUBMED_FIELDS.map((field) => [field.group, PUBMED_FIELDS.filter((item) => item.group === field.group)])
  ).entries()
).map(([label, fields]) => ({ label, fields }));

export function formatPubMedSearchTerm(term: string, fieldId: string) {
  const value = term.trim();
  if (!value) return "";

  const field = PUBMED_FIELD_MAP[fieldId] ?? PUBMED_FIELD_MAP.all;
  if (!field) return value;

  if (field.behavior === "raw") {
    return value;
  }

  if (field.behavior === "owner") {
    return value.toLowerCase().startsWith("owner") ? value : `owner${value}`;
  }

  if (field.tag === "all") {
    return value;
  }

  return `${value}[${field.tag}]`;
}
