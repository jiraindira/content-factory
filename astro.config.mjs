// @ts-check
import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

import { wrapMethodologyCallout } from "./src/lib/remark/wrapMethodologyCallout.ts";

console.log("[astro.config] methodology plugin is", typeof wrapMethodologyCallout);

export default defineConfig({
  site: "http://localhost:4321",
  integrations: [tailwind()],
  markdown: {
    // wrappers only
    remarkPlugins: [wrapMethodologyCallout],
  },
});
