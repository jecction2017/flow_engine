/**
 * 上下文映射：测试中心（lookup 行 / 方案）与运行中心（消息触发入参）共用语义。
 */

import type { ContextMapping } from "@/api/testBatches";

export type ContextMappingMode = "spread" | "wrap" | "rules" | "script";

export type ContextMappingState = ContextMapping;

/** @deprecated 与 ContextMappingState 相同 */
export type IngressMappingState = ContextMappingState;

/** @deprecated 与 ContextMappingMode 相同 */
export type IngressMappingMode = ContextMappingMode;

export type MappingSurface = "test" | "ingress";

export const DEFAULT_WRAP_KEY = "payload";

export const DEFAULT_SCRIPT_TEXT =
  'payload\n\n{\n  "工单": payload["alert"] if "alert" in payload else payload,\n}';

export const DEFAULT_CONTEXT_MAPPING_TEST: ContextMappingState = { mode: "spread" };

export const DEFAULT_INGRESS_MAPPING: ContextMappingState = {
  mode: "wrap",
  wrap_key: DEFAULT_WRAP_KEY,
  wrap_as_list: false,
};

export const DEFAULT_MAPPING_RULES: Array<{ source: string; target: string }> = [
  { source: "alert_id", target: "case.id" },
  { source: "severity", target: "case.severity" },
  { source: "title", target: "case.title" },
];

export const MAPPING_SAMPLE_JSON =
  '{\n  "alert_id": "ALT-2026-001",\n  "severity": "HIGH",\n  "title": "可疑登录"\n}';

export const MAPPING_MODE_OPTIONS: Array<{
  value: ContextMappingMode;
  label: string;
  tech: string;
}> = [
  { value: "spread", label: "展开到流程变量", tech: "spread" },
  { value: "wrap", label: "打包进变量", tech: "wrap" },
  { value: "rules", label: "按字段映射", tech: "rules" },
  { value: "script", label: "自定义映射（Starlark）", tech: "script" },
];

export function mappingModeHint(mode: ContextMappingMode, wrapKey: string, surface: MappingSurface): string {
  if (mode === "spread") {
    return surface === "ingress"
      ? "消息 JSON 各顶层字段直接写入流程变量。"
      : "Lookup 行 / 样例 JSON 各顶层字段直接展开为流程变量。";
  }
  if (mode === "wrap") {
    return `整包写入变量 ${wrapKey}，流程内通过 ${wrapKey}.字段名 访问。`;
  }
  if (mode === "rules") {
    return "按规则将来源字段写入流程变量路径（支持点路径，如 case.id）。";
  }
  return surface === "ingress"
    ? "Starlark 须返回 dict；全局变量 payload 为解码后的消息 JSON。"
    : "Starlark 须返回 dict；全局变量 payload 为 lookup 行 / 样例 JSON。";
}

export function defaultWrapKey(_surface: MappingSurface): string {
  return DEFAULT_WRAP_KEY;
}

export function createMappingForMode(
  mode: ContextMappingMode,
  surface: MappingSurface,
  prev?: ContextMappingState,
): ContextMappingState {
  if (mode === "script") {
    const script =
      prev?.mode === "script" && prev.script.trim() ? prev.script : DEFAULT_SCRIPT_TEXT;
    return { mode: "script", script };
  }
  if (mode === "spread") return { mode: "spread" };
  if (mode === "wrap") {
    const wrap_key =
      prev?.mode === "wrap" && prev.wrap_key.trim() ? prev.wrap_key.trim() : defaultWrapKey(surface);
    const wrap_as_list = prev?.mode === "wrap" ? !!prev.wrap_as_list : false;
    return { mode: "wrap", wrap_key, wrap_as_list };
  }
  const rules =
    prev?.mode === "rules" && prev.rules.length > 0
      ? prev.rules.map((r) => ({ ...r }))
      : DEFAULT_MAPPING_RULES.map((r) => ({ ...r }));
  return { mode: "rules", rules };
}

export function replaceMappingState(target: ContextMappingState, next: ContextMappingState): void {
  const t = target as Record<string, unknown>;
  for (const k of Object.keys(t)) delete t[k];
  Object.assign(t, next);
}

export function validateContextMapping(
  mapping: ContextMappingState,
): { ok: true } | { ok: false; error: string } {
  if (mapping.mode === "script") {
    if (!mapping.script.trim()) {
      return { ok: false, error: "自定义映射（Starlark）须填写脚本" };
    }
    return { ok: true };
  }
  if (mapping.mode === "wrap" && !mapping.wrap_key.trim()) {
    return { ok: false, error: "打包进变量模式下请填写流程变量名" };
  }
  if (mapping.mode === "rules" && !mapping.rules.length) {
    return { ok: false, error: "按字段映射模式下请至少添加一条映射规则" };
  }
  return { ok: true };
}

/** @deprecated 使用 validateContextMapping */
export const validateIngressMapping = validateContextMapping;

/** 订阅 schedule_config.parse 段 */
export function buildParseSectionFromIngressMapping(
  mapping: ContextMappingState,
): { ok: true; parse: Record<string, unknown> } | { ok: false; error: string } {
  const v = validateContextMapping(mapping);
  if (!v.ok) return v;
  if (mapping.mode === "script") {
    return {
      ok: true,
      parse: { codec: "json", transform: "script", script: mapping.script },
    };
  }
  return {
    ok: true,
    parse: {
      codec: "json",
      transform: "mapping",
      mapping: { ...mapping } as Record<string, unknown>,
    },
  };
}
