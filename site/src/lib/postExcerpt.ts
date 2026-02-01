import type { CollectionEntry } from "astro:content";

function stripMarkdown(text: string): string {
  let s = String(text ?? "");
  // Remove HTML comments
  s = s.replace(/<!--([\s\S]*?)-->/g, " ");
  // Links: [text](url) -> text
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
  // Inline code/backticks/emphasis markers
  s = s.replace(/[`*_]/g, "");
  // Basic HTML tags
  s = s.replace(/<[^>]+>/g, " ");
  // Collapse whitespace
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

function truncateSmart(text: string, maxChars: number): string {
  const s = String(text ?? "").trim();
  if (!s) return "";
  if (s.length <= maxChars) return s;

  // Prefer first sentence if it fits.
  const m = s.match(/^(.+?[.!?])\s/);
  if (m && m[1].length >= 60 && m[1].length <= maxChars) {
    return m[1].trim();
  }

  // Otherwise, word-boundary truncate.
  const cut = s.slice(0, maxChars).trim();
  const lastSpace = cut.lastIndexOf(" ");
  const out = (lastSpace > 60 ? cut.slice(0, lastSpace) : cut).trim();
  return out.replace(/[\s.,;:!-]+$/, "");
}

export function isGenericDescription(desc: unknown): boolean {
  const s = typeof desc === "string" ? desc.trim() : "";
  if (!s) return true;
  return /^curated\s+.+\s+picks\s+for\s+/i.test(s);
}

export function extractIntroExcerptFromBody(body: unknown): string {
  const md = String(body ?? "");
  const lines = md.split("\n");

  // Try to find "## Intro"; if missing, just use the first paragraph.
  let start = 0;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*##\s+intro\s*$/i.test(lines[i] ?? "")) {
      start = i + 1;
      break;
    }
  }

  // Skip leading blanks
  while (start < lines.length && !(lines[start] ?? "").trim()) start++;

  const para: string[] = [];
  for (let i = start; i < lines.length; i++) {
    const ln = lines[i] ?? "";
    if (/^\s*##\s+/.test(ln)) break;
    if (!ln.trim()) {
      if (para.length) break;
      continue;
    }
    para.push(ln.trim());
  }

  return stripMarkdown(para.join(" "));
}

export function getPostCardDescription(post: CollectionEntry<"posts">, maxChars = 140): string {
  const desc = typeof post?.data?.description === "string" ? post.data.description.trim() : "";
  if (desc && !isGenericDescription(desc)) return desc;

  const excerpt = extractIntroExcerptFromBody(post?.body);
  return truncateSmart(excerpt, maxChars);
}
