import {
  autocompletion,
  type Completion,
  type CompletionContext,
} from "@codemirror/autocomplete";

/**
 * 仅返回 ``$.`` 路径补全 source，便于与 Starlark registry 补全合并到同一 ``autocompletion``。
 */
export function contextPathCompletionSource(getPaths: () => readonly string[]) {
  return (context: CompletionContext) => {
    const before = context.matchBefore(/\$\.[\w.]*$/);
    if (!before && !context.explicit) return null;

    const paths = [...new Set(getPaths())].sort((a, b) => a.localeCompare(b));
    const prefix = before ? before.text : "$.";
    const from = before ? before.from : context.pos;

    const options: Completion[] = paths
      .filter((p) => !prefix || p.startsWith(prefix))
      .map((p) => ({
        label: p,
        type: "keyword" as const,
        detail: "上下文路径",
      }));

    if (!options.length) return null;
    return { from, options, filter: false };
  };
}

/** 仅路径补全（无 Starlark registry 时使用）。 */
export function contextPathAutocomplete(getPaths: () => readonly string[]) {
  return autocompletion({
    override: [contextPathCompletionSource(getPaths)],
    activateOnTyping: true,
    maxRenderedOptions: 100,
  });
}
