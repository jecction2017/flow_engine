/** Registry-driven completions for Starlark task scripts (Python builtins + internal exports). */

import {
  autocompletion,
  completeAnyWord,
  type Completion,
  type CompletionContext,
  type CompletionSource,
} from "@codemirror/autocomplete";
import type { RegistryDoc, RegistryPythonFn } from "@/api/starlark";
import { contextPathCompletionSource } from "@/codemirror/contextPathAutocomplete";

function buildBuiltinCompletionInfo(f: RegistryPythonFn): string {
  const lines = [
    f.summary,
    "",
    `签名: ${f.starlark_name}${formatSignature(f.signature)}`,
    `返回: ${f.returns}`,
    `类目: ${f.category}`,
  ];
  if (f.attach_mode === "context") {
    lines.push("", "运行时由引擎注入上下文绑定；在任务/条件/Hook 脚本中直接调用。");
  } else if (f.attach_mode === "flow_control") {
    lines.push("", "流程控制：中断当前脚本并交由编排器处理（非普通返回值）。");
  } else if (f.side_effects && f.side_effects !== "none") {
    lines.push("", `副作用: ${f.side_effects}（调试/试运行下可能 SUPPRESS）`);
  } else {
    lines.push("", "在任务脚本中直接调用，无需 load。");
  }
  lines.push("", `id: ${f.id}`);
  return lines.join("\n");
}

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
          info: buildBuiltinCompletionInfo(f),
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

/** CodeMirror extension：可选上下文路径（``$.``）+ registry + 词内补全。 */
export function flowRegistryAutocompletion(
  registry: RegistryDoc | null,
  getPaths?: (() => readonly string[]) | null,
) {
  const sources: CompletionSource[] = [completeAnyWord];
  if (registry) sources.unshift(completionSource(registry));
  if (getPaths) sources.unshift(contextPathCompletionSource(getPaths));
  return autocompletion({
    override: sources,
    activateOnTyping: true,
    maxRenderedOptions: 120,
  });
}
