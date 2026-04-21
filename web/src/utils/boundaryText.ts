/**
 * 任务节点「边界映射」的文本格式（单一文本框，YAML 风格）。
 *
 * 期望结构：
 *
 *   inputs:
 *     $.global.alert: alert
 *     $.item: alarm
 *   outputs:
 *     summary: $.global.summary
 *     row: $.global.row
 *
 * 解析规则：
 *   - 顶级键只能是 ``inputs`` 或 ``outputs``，二者都可选；未出现则视为空集。
 *   - 顶级键所在行不允许出现映射内容；允许 ``inputs:`` 或 ``inputs: {}``（= 空）。
 *   - 其它行若有前导空白，则属于当前节；首个 ``:`` 作为 key/value 分隔符。
 *   - 空行与以 ``#`` 起始的行视为注释，解析时忽略。
 *   - inputs：key 必须以 ``$.`` 开头（上下文路径），value 必须是合法 Starlark 标识符。
 *   - outputs：key 必须是字段名（允许点号链式），value 必须以 ``$.`` 开头。
 *
 * 预留：未来可在 value 位置支持内嵌对象字面量（如
 * ``$.item: {var: alarm, required: true, type: dict}``）承载输入/输出的约束信息，
 * 不需要改动文本格式的总体结构。
 */

export interface BoundaryMapping {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

export interface BoundaryDocParseResult {
  /** 解析成功时的结构化结果；失败时保证返回空 inputs/outputs（调用方可选择丢弃）。 */
  data: BoundaryMapping;
  /** 行级的人类可读错误信息；``[]`` 表示校验通过。 */
  errors: string[];
}

type Section = "inputs" | "outputs";

const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const OUTPUT_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/;
const CONTEXT_PATH_RE = /^\$\.[^\s]+/;

function splitFirstColon(s: string): { key: string; value: string } | null {
  const idx = s.indexOf(":");
  if (idx < 0) return null;
  return { key: s.slice(0, idx).trim(), value: s.slice(idx + 1).trim() };
}

function validatePair(section: Section, k: string, v: string): string | null {
  if (section === "inputs") {
    if (!CONTEXT_PATH_RE.test(k)) return `inputs 的 key 必须以 "$." 开头（上下文路径），收到 "${k}"`;
    if (!IDENT_RE.test(v)) return `inputs 的 value 必须是合法 Starlark 变量名，收到 "${v}"`;
  } else {
    if (!OUTPUT_KEY_RE.test(k)) {
      return `outputs 的 key 必须是字段名（可含点号链式），字母/下划线开头：收到 "${k}"`;
    }
    if (!CONTEXT_PATH_RE.test(v)) return `outputs 的 value 必须以 "$." 开头（上下文路径），收到 "${v}"`;
  }
  return null;
}

/** 解析完整的边界映射文本文档。 */
export function parseBoundaryDoc(text: string): BoundaryDocParseResult {
  const data: BoundaryMapping = { inputs: {}, outputs: {} };
  const errors: string[] = [];
  const lines = text.split(/\r?\n/);

  let section: Section | null = null;
  const seenSections = new Set<Section>();

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const leadingWs = raw.length - raw.trimStart().length;

    if (leadingWs === 0) {
      // 顶级行：必须是 ``inputs:`` 或 ``outputs:``（允许 ``{}`` 的空占位）。
      const pair = splitFirstColon(trimmed);
      if (!pair) {
        errors.push(`第 ${i + 1} 行无法解析："${trimmed}"（缺少 ":"）`);
        section = null;
        continue;
      }
      const keyLower = pair.key.toLowerCase();
      if (keyLower !== "inputs" && keyLower !== "outputs") {
        errors.push(`第 ${i + 1} 行未知顶级键 "${pair.key}"，仅支持 "inputs" 与 "outputs"`);
        section = null;
        continue;
      }
      const sec = keyLower as Section;
      if (seenSections.has(sec)) {
        errors.push(`第 ${i + 1} 行 "${sec}" 重复出现`);
      }
      seenSections.add(sec);
      section = sec;
      if (pair.value && pair.value !== "{}") {
        errors.push(
          `第 ${i + 1} 行 "${sec}:" 后不应出现内容（可写 "${sec}:" 或 "${sec}: {}" 表示空集）`,
        );
      }
      continue;
    }

    // 缩进行：必须处于某个 section 内。
    if (section === null) {
      errors.push(
        `第 ${i + 1} 行缺少顶级节：请将映射放在 "inputs:" 或 "outputs:" 下方缩进书写`,
      );
      continue;
    }
    const pair = splitFirstColon(trimmed);
    if (!pair) {
      errors.push(`第 ${i + 1} 行无法解析（缺少 ":"），收到 "${trimmed}"`);
      continue;
    }
    if (!pair.key) {
      errors.push(`第 ${i + 1} 行 key 为空："${trimmed}"`);
      continue;
    }
    if (!pair.value) {
      errors.push(`第 ${i + 1} 行 value 为空："${trimmed}"`);
      continue;
    }
    const msg = validatePair(section, pair.key, pair.value);
    if (msg) {
      errors.push(`第 ${i + 1} 行：${msg}`);
      continue;
    }
    const bucket = data[section];
    if (Object.prototype.hasOwnProperty.call(bucket, pair.key)) {
      errors.push(`第 ${i + 1} 行 key 重复："${pair.key}"（当前节 "${section}"）`);
      continue;
    }
    bucket[pair.key] = pair.value;
  }

  if (errors.length > 0) return { data: { inputs: {}, outputs: {} }, errors };
  return { data, errors: [] };
}

/** 将结构化边界映射序列化为文本文档；两节同时为空时输出空骨架便于编辑。 */
export function serializeBoundaryDoc(m: BoundaryMapping | undefined | null): string {
  const inputs = m?.inputs ?? {};
  const outputs = m?.outputs ?? {};
  const renderSection = (name: Section, dict: Record<string, string>) => {
    const entries = Object.entries(dict);
    if (entries.length === 0) return `${name}: {}`;
    const body = entries.map(([k, v]) => `  ${k}: ${v}`).join("\n");
    return `${name}:\n${body}`;
  };
  return `${renderSection("inputs", inputs)}\n${renderSection("outputs", outputs)}`;
}
