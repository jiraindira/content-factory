# AI Content Factory — Error Reference (v1)

This project hard-fails on invalid configuration and compliance constraints.

## Common errors

### Brand validation

- `brand_sources.sources must not be empty`
  - Add at least one brand source.

- `brand_sources must include at least one source with purpose in ...`
  - Ensure at least one source matches a required purpose (commonly `homepage` or `linkedin_profile`).

- `topic_policy.allowlist must not be empty`
  - Provide at least one topic.

- `disclaimer_policy.disclaimer_text is required when required=true`
  - Required disclaimers must include text and locations.

### Request validation

- `publish.publish_date must be today-or-future`
  - The system uses local system time; past dates are rejected.

- `delivery_target.channel ... not allowed by brand`
- `delivery_target.destination ... not allowed by brand`
  - Update the request to match `delivery_policy` in the brand profile.

- `products.mode must be manual_list for product recommendation forms (v1)`
  - Product runs require `manual_list` and at least one item.

- `products.mode must be none for non-product forms`
  - Thought leadership runs must not include products.

### Robots / source ingestion

- `Brand source ingestion failed: ... robots.txt disallowed`
  - One or more sources disallow fetching for User-Agent `AIContentFactoryFetcher-1.0`.
  - Remove/replace the source or update allowed sources.

### Adapter validation

- `Adapter channel mismatch` / `Adapter destination mismatch`
  - Your request delivery target does not match the adapter you are trying to render.

## Debugging tips

- Start by running `poetry run python -m unittest`.
- Validate brand + request before building context or running.
- If context builds fail, check each configured `brand_sources` URL in a browser and review its robots.txt.
