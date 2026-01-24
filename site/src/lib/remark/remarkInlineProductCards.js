import { visit } from "unist-util-visit";

const PICK_MARK_RE = /<!--\s*pick_id:\s*([a-z0-9\-_:]+)\s*-->/i;

export function remarkInlineProductCards() {
  return (tree, vfile) => {
    const fm =
      (vfile && vfile.data && vfile.data.astro && vfile.data.astro.frontmatter) || {};
    const products = Array.isArray(fm.products) ? fm.products : [];
    if (!products.length) return;

    const byPickId = new Map();
    for (const p of products) {
      const pickId = typeof p?.pick_id === "string" ? p.pick_id.trim() : "";
      if (pickId) byPickId.set(pickId, p);
    }

    visit(tree, "heading", (node, index, parent) => {
      if (!parent || typeof index !== "number") return;
      if (node.depth !== 3) return;

      // Look for a preceding html node containing the pick marker
      const prev = parent.children[index - 1];
      const prevHtml = prev && prev.type === "html" ? String(prev.value || "") : "";
      const m = prevHtml.match(PICK_MARK_RE);
      if (!m) return;

      const pickId = m[1].trim();
      const product = byPickId.get(pickId);
      if (!product) return;

      const html = renderInlineCardHtml(product);

      parent.children.splice(index + 1, 0, {
        type: "html",
        value: html,
      });
    });
  };
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function hostname(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function renderInlineCardHtml(product) {
  const title = typeof product?.title === "string" ? product.title.trim() : "";
  const url = typeof product?.url === "string" ? product.url.trim() : "";
  const hasUrl = Boolean(url);

  const site = hasUrl ? hostname(url) : "";
  const initials =
    title
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || "P";

  const ratingOk = typeof product?.rating === "number" && product.rating > 0;
  const reviewsOk = typeof product?.reviews_count === "number" && product.reviews_count > 0;
  const priceOk = typeof product?.price === "string" && product.price.trim().length > 0 && product.price !== "—";

  const metaParts = [];
  if (ratingOk) metaParts.push(`${product.rating.toFixed(1)}★`);
  if (reviewsOk) metaParts.push(`${Number(product.reviews_count).toLocaleString()} reviews`);
  if (priceOk) metaParts.push(escapeHtml(product.price));
  const metaLine = metaParts.join(" · ");

  // IMPORTANT: In manual mode, if no affiliate url exists yet, we show a disabled button.
  return `
<div class="inline-pick-card" data-inline-pick>
  <div class="inline-pick-row">
    <div class="inline-pick-badge" aria-hidden="true">
      <div class="inline-pick-badge-inner">
        <span class="inline-pick-initials">${escapeHtml(initials)}</span>
      </div>
    </div>

    <div class="inline-pick-main">
      <div class="inline-pick-top">
        <div class="inline-pick-head">
          <div class="inline-pick-kicker">
            ${escapeHtml(site || "amazon.co.uk")}
          </div>
          ${metaLine ? `<div class="inline-pick-meta">${metaLine}</div>` : ""}
        </div>

        <div class="inline-pick-cta">
          ${
            hasUrl
              ? `<a href="${escapeHtml(url)}" target="_blank" rel="sponsored nofollow noopener" class="inline-btn inline-btn-primary">Buy →</a>`
              : `<span class="inline-btn inline-btn-disabled" aria-disabled="true">Link needed</span>`
          }
        </div>
      </div>
    </div>
  </div>
</div>
`.trim();
}
