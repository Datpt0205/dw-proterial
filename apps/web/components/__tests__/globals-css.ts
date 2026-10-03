import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import postcss, { type AcceptedPlugin, type Root } from "postcss";
import config from "../../postcss.config.mjs";

export const GLOBALS = fileURLToPath(
  new URL("../../app/globals.css", import.meta.url),
);

/**
 * `globals.css` as the build compiles it: through the plugins
 * `postcss.config.mjs` names, read from there rather than listed again here.
 * A plugin added to the build (one that rewrites cascade layers, say) is then
 * a plugin these tests compile with too.
 */
export async function compiledGlobals(): Promise<Root> {
  const plugins = await Promise.all(
    Object.entries(config.plugins).map(async ([name, options]) => {
      const { default: plugin } = (await import(name)) as {
        default: (options: unknown) => AcceptedPlugin;
      };
      return plugin(options);
    }),
  );
  const css = await readFile(GLOBALS, "utf8");
  return (await postcss(plugins).process(css, { from: GLOBALS })).root;
}
