/**
 * Where generated components look for `cn`.
 *
 * shadcn writes `import { cn } from "@/lib/cn"` into everything it copies in.
 * The real implementation is `@dw/ui`'s, shared with the rest of the app - a
 * second `twMerge(clsx(...))` here would be the same function under a second
 * name, and the day they drifted nobody would know which one a component used.
 *
 * Known quirk, and it bites every time: because this alias is not the
 * conventional `@/lib/utils`, `shadcn add` mis-reads it and emits a bare
 * `import { cn } from "cn"` in some files - then installs an unrelated npm
 * package of that name to satisfy it. After any `shadcn add`, grep for
 * `from "cn"` and point it back here.
 */
export { cn } from "@dw/ui";
