import { defineCollection, z } from "astro:content";

/**
 * POSTS COLLECTION
 * - publishedAt is ALWAYS a Date at runtime
 * - schema is strict enough to protect UI contracts
 * - no surprise unions, no runtime guessing
 */
const posts = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    description: z.string(),

    // ✅ CRITICAL FIX:
    // Always coerce to Date so .getTime() is safe everywhere
    publishedAt: z.coerce.date(),

    category: z.string().optional(),
    audience: z.string().optional(),

    heroImage: z.string().optional(),
    heroAlt: z.string().optional(),
    imageCreditName: z.string().optional(),
    imageCreditUrl: z.string().optional(),

    // Products drive ALL pick UI + sidebar + cards
    products: z
      .array(
        z.object({
          pick_id: z.string(),
          catalog_key: z.string().nullable().optional(),
          title: z.string(),

          // Must be a valid URL or Astro will hard-fail
          url: z.string().url(),

          price: z.string().optional(),
          rating: z.number().optional(),
          reviews_count: z.number().optional(),
          description: z.string().optional(),
        }),
      )
      .default([]),

    /**
     * Picks are optional metadata for future use.
     * They are NOT rendered directly today,
     * but keeping them avoids migration pain later.
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
