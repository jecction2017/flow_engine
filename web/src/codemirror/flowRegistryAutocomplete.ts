/** Registry-driven completions for Starlark task scripts (Python builtins + internal exports). */

import {
  autocompletion,
  completeAnyWord,
  type Completion,
  type CompletionContext,
} from "@codemirror/autocomplete";
import type { RegistryDoc } from "@/api/starlark";

function formatSignature(
  signature: Array<{ name: string; type: string; required?: boolean }>,
): string {
  if (!signature.length) return "()";
  const args = signature.map((p) => {
    const t = p.type?.trim() || "any";
    if (p.required === false) return `${p.name}?: ${t}`;
    return `${p.name}: ${t}`;
  });
  return `(${args.join(", ")})`;
}

function completionSource(registry: RegistryDoc) {
  return (context: CompletionContext) => {
    const word = context.matchBefore(/[\w_]*/);
    if (word == null) return null;
    if (word.from === word.to && !context.explicit) return null;

    const prefix = word.text.toLowerCase();
    const options: Completion[] = [];

    for (const f of registry.python_functions) {
      const l = f.starlark_name;
      if (!prefix || l.toLowerCase().startsWith(prefix)) {
        options.push({
          label: l,
          type: "function",
          detail: `${l}${formatSignature(f.signature)}`,
          info: `${f.summary}\n\n签名: ${l}${formatSignature(f.signature)}\n返回: ${f.returns}\n\n• id: ${f.id}\n• 在任务脚本中直接调用，无需 load。`,
        });
      }
    }

    for (const m of registry.internal_modules) {
      for (const ex of m.exports) {
        if (!prefix || ex.toLowerCase().startsWith(prefix)) {
          options.push({
            label: ex,
            type: "variable",
            detail: `← ${m.uri}`,
            info: `${m.summary}\n\n先 load 再使用，例如：\nload("${m.uri}", ${m.exports.map((e) => `"${e}"`).join(", ")})`,
          });
        }
      }
    }

    options.sort((a, b) => a.label.localeCompare(b.label));

    return { from: word.from, options, filter: false };
  };
}

/** CodeMirror extension; pass null to skip (no extra completions). */
export function flowRegistryAutocompletion(registry: RegistryDoc | null) {
  const sources = [completeAnyWord];
  if (registry) sources.unshift(completionSource(registry));
  return autocompletion({
    // include both:
    // 1) registry-driven builtins/internal exports
    // 2) in-document identifiers (variables/functions defined above)
    override: sources,
    activateOnTyping: true,
    maxRenderedOptions: 120,
  });
}
