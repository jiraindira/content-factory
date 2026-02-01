# AI Content Factory — Client Onboarding

This system onboards clients via YAML.

## What you need from a client

- `brand_id` (stable identifier)
- Allowed domains (e.g. `leadership`, `tech`)
- Voice + persona preferences (mapped to enums)
- Topic allowlist (required)
- Required disclaimers/disclosures (required)
- Brand sources (URLs/files) for `BrandContextArtifact` (robots.txt enforced)

## Step-by-step

### 1) Scaffold brand + request

```bash
poetry run content-factory onboard \
  --brand-id acme_consulting \
  --domains-supported leadership \
  --domain-primary leadership
```

Outputs:

- `content_factory/brands/acme_consulting.yaml`
- `content_factory/requests/acme_consulting_<date>.yaml`

### 2) Fill in real values

Edit the generated YAML files:

- Replace `topic_policy.allowlist` placeholders
- Set correct `delivery_policy` (channels/destinations)
- Add real `brand_sources` references
- Confirm disclaimers and commercial policy

### 3) Validate

```bash
poetry run content-factory validate-brand --brand content_factory/brands/acme_consulting.yaml
poetry run content-factory validate-request \
  --brand content_factory/brands/acme_consulting.yaml \
  --request content_factory/requests/acme_consulting_<date>.yaml
```

### 4) Build brand context (cached)

```bash
poetry run content-factory build-context --brand content_factory/brands/acme_consulting.yaml
```

Output:

- `content_factory/artifacts/acme_consulting.json`

### 5) Run

```bash
poetry run content-factory run \
  --brand content_factory/brands/acme_consulting.yaml \
  --request content_factory/requests/acme_consulting_<date>.yaml
```

Outputs:

- `content_factory/outputs/<run_id>.json` (ContentArtifact)
- `content_factory/outputs/<run_id>.*` (delivery output)

## Notes

- Brand source fetching is read-only and robots.txt enforced for User-Agent `AIContentFactoryFetcher-1.0`.
- Past publish dates hard-fail (local system time).
- Topics are allowlist-only.
