# AI Affiliate Engine

Deterministic, agent-assisted pipeline for generating affiliate blog posts.

This repo supports **manual** and **automated (future)** workflows.  
The manual workflow is optimized for control: *you provide the products, agents do the writing.*

---

## Manual pipeline (current, single step)

### What you edit

You provide all inputs up-front in a single file:

data/inputs/manual/post_input.json


Minimal example (extend as needed):

```json
{
  "category": "electronics",
  "subcategory": "item_finders",
  "audience": "UK shoppers",
  "products": [
    {
      "title": "Apple AirTag",
      "url": "https://amzn.to/example",
      "price": "£29",
      "rating": 4.7,
      "reviews_count": 120000,
      "description": "Bluetooth tracker for keys, bags, and luggage"
    },
    {
      "title": "Tile Mate (2024)",
      "url": "https://amzn.to/example2",
      "price": "£25",
      "rating": 4.4,
      "reviews_count": 54000,
      "description": "Bluetooth tracker for everyday items"
    }
  ]
}

Required per product

title
url
rating
reviews_count

Optional
price
description

2. Generate the post (single command)
poetry run python -m scripts.write_manual_post

Optional flags:
poetry run python -m scripts.write_manual_post --dry-run
poetry run python -m scripts.write_manual_post --date 2026-01-25
poetry run python -m scripts.write_manual_post --input data/inputs/manual/post_input.json

Defaults:
--date → today
--input → data/inputs/manual/post_input.json

3. Output

A fully-written post is created at:
site/src/content/posts/<date>-<slug>.md

Each post includes:
Astro frontmatter (title, description, hero image, products)
Structured product cards
Affiliate links
Long-form copy
QA pass (non-blocking)

What the pipeline does

When you run write_manual_post, the system:
Reads post_input.json
Generates a title and slug
Ensures products exist in the catalog
Builds an Astro markdown scaffold
Expands content using LLM agents
Generates a hero image
Runs Preflight QA (+ optional repair)
Writes the final .md file