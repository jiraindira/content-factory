import { defineCollection, z } from "astro:content";

/**
 * POSTS COLLECTION
 * - publishedAt is ALWAYS a Date at runtime
 * - schema is strict enough to protect UI contracts
 * - supports multi-category posts (categories[])
 * - keeps legacy category for back-compat
 */
const posts = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    description: z.string(),

    // Always coerce to Date so .getTime() is safe everywhere
    publishedAt: z.coerce.date(),

    /**
     * ✅ Multi-category (new)
     * Canonical field going forward.
     */
    categories: z.array(z.string()).default([]),

    /**
     * ✅ Legacy single category (old)
     * Kept for backwards compatibility and easy transitions.
     */
    category: z.string().optional(),

    audience: z.string().optional(),

    heroImage: z.string().optional(),
    heroImageHome: z.string().optional(),
    heroImageCard: z.string().optional(),
    heroImageSource: z.string().optional(),

    heroAlt: z.string().optional(),
    imageCreditName: z.string().optional(),
    imageCreditUrl: z.string().optional(),

    // Optional UI metadata
    readingTime: z.number().optional(),
    toc: z.array(z.any()).optional(),

    // Products drive ALL pick UI + sidebar + cards
    products: z
      .array(
        z.object({
          pick_id: z.string(),
          catalog_key: z.string().nullable().optional(),
          title: z.string(),

          /**
           * Contract:
           * - Valid URL => link is usable
           * - "" => link pending (UI should render disabled CTA / placeholder)
           */
          url: z.union([z.string().url(), z.literal("")]).default(""),

          price: z.string().optional(),
          rating: z.number().optional(),
          reviews_count: z.number().optional(),
          description: z.string().optional(),
        }),
      )
      .default([]),

    /**
     * Picks are optional metadata for future use.
     */
    picks: z
      .array(
        z.object({
          pick_id: z.string(),
          body: z.string().default(""),
        }),
      )
      .default([]),
  }),
});

/**
 * SITE DATA COLLECTION
 * - taxonomy.json lives here
 * - passthrough so you can evolve structure freely
 */
const site = defineCollection({
  type: "data",
  schema: z.object({}).passthrough(),
});

export const collections = {
  posts,
  site,
};
