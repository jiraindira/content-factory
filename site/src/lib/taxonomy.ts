import { getEntry } from "astro:content";

export type TaxonomyCategory = {
  id: string;
  label: string;
  aliases?: string[];
  subcategories?: any[];
};

export type TaxonomyGroup = {
  key: string;
  label: string;
  intro?: string;

  // Back-compat: old configs had `categories`, new ones use `categoryIds`
  categories?: unknown[];
  categoryIds?: unknown[];
};

export type Taxonomy = {
  brand: { name: string; tagline: string };

  // Optional richer categories model (fine if absent)
  categories?: TaxonomyCategory[];

  // Optional alias map (fine if absent)
  aliases?: Record<string, string>;

  groups: TaxonomyGroup[];

  homepage?: any;
};

export async function getTaxonomy(): Promise<Taxonomy> {
  const entry = await getEntry("site", "taxonomy");
  if (!entry) throw new Error("Missing site taxonomy: src/content/site/taxonomy.json");
  return entry.data as Taxonomy;
}

function norm(x: unknown): string {
  return String(x ?? "").trim().toLowerCase();
}

function coerceCategoryId(x: unknown): string {
  if (typeof x === "string") return x;

  if (x && typeof x === "object") {
    const obj = x as any;
    if (typeof obj.id === "string") return obj.id;
    if (typeof obj.key === "string") return obj.key;
    if (typeof obj.label === "string") return obj.label;
  }

  return String(x ?? "");
}

/**
 * Pretty-print a category id or label.
 * Safe for unknown inputs (string | object | null).
 */
export function prettyCategory(input: unknown): string {
  const s0 = coerceCategoryId(input);
  const s = String(s0 ?? "").trim();
  if (!s) return "";

  return s
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bAnd\b/g, "&");
}

/**
 * Resolve category ids using:
 * - taxonomy.aliases (e.g. gadgets -> tech)
 * - taxonomy.categories[].aliases (optional)
 */
export function resolveCategoryId(taxonomy: Taxonomy, raw: unknown): string {
  const s = norm(coerceCategoryId(raw));
  if (!s) return "";

  // aliases map
  const map = taxonomy.aliases ?? {};
  const mapped = map[s];
  if (mapped) return norm(mapped);

  // categories model with aliases
  const cats = taxonomy.categories ?? [];
  const direct = cats.find((c) => norm(c.id) === s);
  if (direct) return norm(direct.id);

  const viaAlias = cats.find((c) => (c.aliases ?? []).map(norm).includes(s));
  if (viaAlias) return norm(viaAlias.id);

  // Unknown: keep as-is
  return s;
}

/**
 * Preferred label for UI:
 * - If taxonomy.categories contains a label, use it
 * - else fall back to prettyCategory(id)
 */
export function categoryLabel(taxonomy: Taxonomy, raw: unknown): string {
  const id = resolveCategoryId(taxonomy, raw);
  if (!id) return "";

  const cats = taxonomy.categories ?? [];
  const found = cats.find((c) => norm(c.id) === norm(id));
  return found?.label ? String(found.label) : prettyCategory(id);
}

/**
 * ✅ Normalize categories on a post.
 * New posts: data.categories = ["pets","home"]
 * Old posts: data.category = "pets"
 */
export function normalizePostCategories(taxonomy: Taxonomy, postData: any): string[] {
  const d = postData ?? {};

  const rawArr = Array.isArray(d.categories)
    ? d.categories
    : d.category
      ? [d.category]
      : [];

  const ids = rawArr
    .map((x: unknown) => resolveCategoryId(taxonomy, x))
    .map(norm)
    .filter(Boolean);

  // de-dupe, preserve order
  const seen = new Set<string>();
  return ids.filter((c) => {
    if (seen.has(c)) return false;
    seen.add(c);
    return true;
  });
}

/**
 * Canonical accessor for group category membership.
 * Accepts BOTH:
 * - group.categoryIds (new)
 * - group.categories (old)
 */
export function groupCategoryIds(taxonomy: Taxonomy, groupKey: string): string[] {
  const g = (taxonomy.groups ?? []).find((x) => norm(x.key) === norm(groupKey));
  const raw = (g?.categoryIds ?? g?.categories ?? []) as unknown[];

  return raw
    .map((x) => resolveCategoryId(taxonomy, x))
    .map(norm)
    .filter(Boolean);
}

/**
 * Back-compat helper for older components.
 */
export function groupForCategory(taxonomy: Taxonomy, category: unknown) {
  const cat = resolveCategoryId(taxonomy, category);
  const g = (taxonomy.groups ?? []).find((x) => groupCategoryIds(taxonomy, x.key).includes(norm(cat)));

  return g
    ? { key: g.key, label: g.label, intro: g.intro ?? "" }
    : { key: "other", label: "Other", intro: "" };
}
