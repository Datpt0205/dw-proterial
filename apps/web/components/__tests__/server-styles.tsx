import type { ReactElement, ReactNode } from "react";
import { renderToString } from "react-dom/server";
// Next's own context: the registry calls `useServerInsertedHTML`, which hands
// its callback to whatever provides this, the way the App Router's server
// render does. Rendering inside it is rendering the root as Next does.
import { ServerInsertedHTMLContext } from "next/dist/shared/lib/server-inserted-html.shared-runtime";
import { UiRoot } from "../ui-root";

type StyleElement = ReactElement<{
  dangerouslySetInnerHTML: { __html: string };
}>;

/**
 * The CSS the app's root ships in the page's head when `children` render on
 * the server: every antd rule and the theme's variables. Call from a test in
 * the node environment, where cssinjs runs in its server mode.
 */
export function serverStyles(children: ReactNode): string {
  const callbacks: Array<() => ReactNode> = [];
  renderToString(
    <ServerInsertedHTMLContext.Provider
      value={(callback: () => ReactNode) => callbacks.push(callback)}
    >
      <UiRoot>{children}</UiRoot>
    </ServerInsertedHTMLContext.Provider>,
  );
  return callbacks
    .map((callback) => callback())
    .filter((node): node is StyleElement => Boolean(node))
    .map((style) => style.props.dangerouslySetInnerHTML.__html)
    .join("\n");
}
