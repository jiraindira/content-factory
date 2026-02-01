# AI Content Factory (and legacy Affiliate Engine)

This repository contains two related systems:

1) **AI Content Factory (current direction):** a spec-driven content compiler that takes a Brand YAML + Request YAML and produces a robust `ContentArtifact` JSON.
2) **Legacy AI Affiliate Engine:** the earlier manual affiliate post pipeline (kept for now).

The project operating contract and milestone plan lives in `ai_content_factory_project_plan.md`.

---

## Quickstart: AI Content Factory (step by step)

### 0) Prerequisites

- Python 3.11+
- (Recommended) Poetry

### 1) Install dependencies

Using Poetry:

```bash
poetry install
```

Or using pip (in a virtualenv):

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 2) Run unit tests (required)

```bash
poetry run python -m unittest
```

### 3) Pick a brand + request (examples included)

- Brand: `content_factory/brands/alisa_amouage.yaml` or `content_factory/brands/everyday_buying_guide.yaml`
- Request: `content_factory/requests/alisa_2026-02-01.yaml` or `content_factory/requests/everyday_buying_guide_2026-02-01.yaml`

### 4) Build the BrandContextArtifact (cached JSON)

This step may fetch live URLs defined in the brand profile and is **robots.txt enforced** with User-Agent `AIContentFactoryFetcher-1.0`.

```bash
poetry run python scripts/build_brand_context.py --brand content_factory/brands/alisa_amouage.yaml
```

Output:

- `content_factory/artifacts/<brand_id>.json`

### 5) Compile a ContentArtifact

This step reads only:

- Brand YAML
- Request YAML
- Cached BrandContextArtifact JSON

```bash
poetry run python scripts/run_content_factory.py \
  --brand content_factory/brands/alisa_amouage.yaml \
  --request content_factory/requests/alisa_2026-02-01.yaml
```

Output:

- `content_factory/outputs/<run_id>.json` (defaults to the request filename stem)

---

## Legacy: Manual affiliate post pipeline

The legacy manual workflow is optimized for control: you provide the products, agents do the writing.

### 1) Edit the input file

`data/inputs/manual/post_input.json`

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
```

Per product:

- Required: `title`, `url`, `rating`, `reviews_count`
- Optional: `price`, `description`

### 2) Generate the post

```bash
poetry run python -m scripts.write_manual_post
```

Optional flags:

```bash
poetry run python -m scripts.write_manual_post --dry-run
poetry run python -m scripts.write_manual_post --date 2026-01-25
poetry run python -m scripts.write_manual_post --input data/inputs/manual/post_input.json
```

### 3) Output

- `site/src/content/posts/<date>-<slug>.md`