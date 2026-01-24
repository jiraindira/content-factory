param(
  [string]$PostsDir = "src/content/posts",
  [string]$Mapping = "data/manual_product_links.json",
  [switch]$DryRun
)

pip install -r requirements-manual-enrichment.txt

$dry = ""
if ($DryRun) { $dry = "--dry-run" }

python services/manual_enrichment/update_product_links.py --posts-dir $PostsDir --mapping $Mapping $dry
