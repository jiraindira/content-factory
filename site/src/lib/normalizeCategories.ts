import type { CollectionEntry } from "astro:content";

/**
 * Minimal shape we need from taxonomy.json
 * (kept loose so the file stays stable even if taxonomy evolves).
 */
type TaxonomyLike = {
  categories?: { id: string }[];
  aliases?: Record<string, string>;
};

function normalizeOne(raw: unknown, taxonomy?: TaxonomyLike): string {
  const s = String(raw ?? "").trim().toLowerCase();
  if (!s) return "";

  const alias = taxonomy?.aliases?.[s];
  return String(alias ?? s).trim().toLowerCase();
}

function _fromPostData(d: any, taxonomy?: TaxonomyLike): string[] {
  const rawList: unknown[] =
    Array.isArray(d?.categories)
      ? d.categories
      : typeof d?.category === "string" && d.category.trim()
        ? [d.category]
        : [];

  let cats = rawList.map((c) => normalizeOne(c, taxonomy)).filter(Boolean);

  // De-dupe while preserving order
  const seen = new Set<string>();
  cats = cats.filter((c) => {
    if (seen.has(c)) return false;
    seen.add(c);
    return true;
  });

  // If taxonomy declares allowed categories, drop unknown ones
  const allowed = (taxonomy?.categories ?? [])
    .map((x) => String(x?.id ?? "").trim().toLowerCase())
    .filter(Boolean);

  if (allowed.length) {
    cats = cats.filter((c) => allowed.includes(c));
  }

  return cats;
}

/**
 * Canonical category normalization.
 *
 * Supports BOTH calling styles (so we don’t have to hunt usages):
 *  A) normalizePostCategories(post, taxonomy)
 *  B) normalizePostCategories(taxonomy, post.data)
 */
export function normalizePostCategories(
  post: CollectionEntry<"posts">,
  taxonomy?: TaxonomyLike,
): string[];
export function normalizePostCategories(
  taxonomy: TaxonomyLike | undefined,
  postData: any,
): string[];
export function normalizePostCategories(a: any, b?: any): string[] {
  // Style A: (post, taxonomy)
  if (a && typeof a === "object" && "data" in a) {
    const post = a as CollectionEntry<"posts">;
    const taxonomy = b as TaxonomyLike | undefined;
    return _fromPostData((post as any).data ?? {}, taxonomy);
  }

  // Style B: (taxonomy, postData)
  const taxonomy = a as TaxonomyLike | undefined;
  const postData = b ?? {};
  return _fromPostData(postData, taxonomy);
}

/**
 * Primary category = first normalized category (if any)
 * Supports BOTH calling styles.
 */
export function primaryCategory(
  post: CollectionEntry<"posts">,
  taxonomy?: TaxonomyLike,
): string;
export function primaryCategory(taxonomy: TaxonomyLike | undefined, postData: any): string;
export function primaryCategory(a: any, b?: any): string {
  // Style A: (post, taxonomy)
  if (a && typeof a === "object" && "data" in a) {
    const post = a as CollectionEntry<"posts">;
    const taxonomy = b as TaxonomyLike | undefined;
    const cats = normalizePostCategories(post, taxonomy);
    return cats[0] ?? "";
  }

  // Style B: (taxonomy, postData)
  const taxonomy = a as TaxonomyLike | undefined;
  const postData = b ?? {};
  const cats = normalizePostCategories(taxonomy, postData);
  return cats[0] ?? "";
}
