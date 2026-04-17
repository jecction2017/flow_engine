<template>
  <div class="guide">
    <aside class="toc">
      <div class="toc-title">脚本帮助</div>
      <a href="#start" class="toc-link">快速开始</a>
      <a href="#syntax" class="toc-link">基础语法</a>
      <a href="#builtins" class="toc-link">内置能力调用</a>
      <a href="#internal" class="toc-link">内置脚本 load</a>
      <a href="#soc" class="toc-link">SOC 实战模板</a>
      <a href="#editor" class="toc-link">编辑器使用</a>
      <a href="#debug" class="toc-link">调试步骤</a>
      <a href="#faq" class="toc-link">常见问题</a>
    </aside>

    <main class="content">
      <section id="start" class="card">
        <h1>任务脚本用户手册</h1>
        <p class="muted">
          面向初学者：你只需要掌握少量 Python 风格语法，就可以在流程节点里编写可运行脚本。
        </p>
        <ol>
          <li>在「能力与脚本 → 用户脚本」创建或打开一个 <code class="mono">租户/xxx.star</code> 文件。</li>
          <li>先写一个返回字典的小脚本。</li>
          <li>点击「调试」查看输出结果，再保存复用。</li>
        </ol>
        <div class="code-box">
          <pre class="code mono">{{ sampleStart }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleStart)">复制</button>
        </div>
      </section>

      <section id="syntax" class="card">
        <h2>1) 基础语法（够用版）</h2>
        <ul>
          <li>变量：<code class="mono">a = 1</code></li>
          <li>字典：<code class="mono">{"k": "v"}</code></li>
          <li>列表：<code class="mono">[1, 2, 3]</code></li>
          <li>条件：<code class="mono">if/else</code></li>
          <li>函数：<code class="mono">def fn(x): return x</code></li>
        </ul>
        <div class="code-box">
          <pre class="code mono">{{ sampleSyntax }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleSyntax)">复制</button>
        </div>
        <p class="tip">任务脚本最后应返回一个字典，流程引擎会把它作为节点输出。</p>
      </section>

      <section id="builtins" class="card">
        <h2>2) Python 内置能力怎么用</h2>
        <p>
          在「能力与脚本 → Python 内置」查看函数说明。常见函数可直接调用，不需要 <code class="mono">load</code>。
        </p>
        <div class="code-box">
          <pre class="code mono">{{ sampleBuiltins }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleBuiltins)">复制</button>
        </div>
        <p class="muted">提示：输入函数名前缀时，编辑器会自动补全并显示参数签名。</p>
      </section>

      <section id="internal" class="card">
        <h2>3) 内置 Starlark 脚本怎么引入</h2>
        <p>通过 <code class="mono">load("internal://...", "...")</code> 引入导出符号：</p>
        <div class="code-box">
          <pre class="code mono">{{ sampleInternal }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleInternal)">复制</button>
        </div>
        <p class="muted">内置脚本是只读的，源码可在「Starlark 内置」分区查看。</p>
      </section>

      <section id="soc" class="card">
        <h2>4) SOC 实战模板（可直接改）</h2>
        <p class="muted">示例：读取告警信息，查询 IOC，输出等级与处置建议。</p>
        <div class="code-box">
          <pre class="code mono">{{ sampleSoc }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleSoc)">复制</button>
        </div>
      </section>

      <section id="editor" class="card">
        <h2>5) 脚本编辑器使用说明</h2>
        <ul>
          <li>支持多行滚动；长脚本可上下滚动查看。</li>
          <li>支持自动补全：内置 Python 函数、internal 导出符号、当前脚本上文变量/函数。</li>
          <li>只读区域（内置脚本源码）不可编辑。</li>
          <li>保存按钮仅在「用户脚本」分区显示。</li>
        </ul>
      </section>

      <section id="debug" class="card">
        <h2>6) 推荐调试步骤</h2>
        <ol>
          <li>先在脚本里返回 1~2 个简单字段，确保结构正确。</li>
          <li>在「调试上下文 JSON」里模拟输入数据。</li>
          <li>观察输出 JSON，逐步增加逻辑。</li>
        </ol>
        <div class="code-box">
          <pre class="code mono">{{ sampleDebugCtx }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleDebugCtx)">复制</button>
        </div>
      </section>

      <section id="faq" class="card">
        <h2>7) 常见问题</h2>
        <h3>Q: 报错 “Task script must evaluate to a dict”</h3>
        <p>A: 你的脚本最终返回值不是字典。请确保末尾结果是 <code class="mono">{...}</code>。</p>
        <h3>Q: 函数没提示怎么办？</h3>
        <p>A: 先输入前缀（如 <code class="mono">dict_</code>），或确认该函数在「Python 内置」列表中存在。</p>
        <h3>Q: internal 函数调用报未定义</h3>
        <p>A: 先写正确的 <code class="mono">load("internal://...", "...")</code> 再使用导出名。</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
const sampleStart = `{"ok": True, "msg": "hello"}`;

const sampleSyntax = `sev = "HIGH"
score = 90

if sev == "HIGH" and score >= 80:
    level = "P1"
else:
    level = "P2"

{"level": level, "score": score}`;

const sampleBuiltins = `n = demo_add(3, 4)
timeout = dict_get("app.http.timeout_sec", 10)

{"sum": n, "timeout": timeout}`;

const sampleInternal = `load("internal://lib/helpers.star", "double_int", "prefix_key")

v = double_int(21)
key = prefix_key("ioc", "ip")

{"value": v, "key": key}`;

const sampleSoc = `# 告警输入（来自调试上下文）
alert = ctx_global.get("alert", {})
sev = alert.get("severity", "LOW")
ioc = alert.get("dest_ip", "")

# 查询 IOC 情报（lookup 命名空间按你们环境调整）
rows = lookup_query("cee", {"ioc": ioc})
hit = rows[0] if rows else {}
intel_level = hit.get("level", "unknown")

# 处置建议
if sev == "HIGH" or intel_level in ["malicious", "high"]:
    action = "escalate_and_block"
    priority = "P1"
else:
    action = "observe"
    priority = "P3"

{
    "ioc": ioc,
    "severity": sev,
    "intel_level": intel_level,
    "priority": priority,
    "action": action
}`;

const sampleDebugCtx = `# 上下文 JSON 示例
{
  "alert": {
    "severity": "HIGH",
    "src_ip": "1.2.3.4",
    "dest_ip": "198.51.100.7"
  }
}`;

async function copyCode(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Ignore clipboard failure to keep UX lightweight.
  }
}
</script>

<style scoped>
.guide {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}

.toc {
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 95%, transparent);
  padding: 14px 12px;
  overflow: auto;
}

.toc-title {
  font-weight: 700;
  margin-bottom: 10px;
}

.toc-link {
  display: block;
  text-decoration: none;
  color: var(--muted);
  font-size: 13px;
  margin: 8px 0;
}

.toc-link:hover {
  color: var(--accent);
}

.content {
  overflow: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: var(--shadow);
}

h1 {
  margin: 0 0 8px;
  font-size: 22px;
}

h2 {
  margin: 0 0 8px;
  font-size: 17px;
}

h3 {
  margin: 12px 0 6px;
  font-size: 14px;
}

p,
li {
  font-size: 13px;
  line-height: 1.5;
}

.muted {
  color: var(--muted);
}

.tip {
  color: var(--success);
}

.code {
  margin: 10px 0 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0f172a;
  color: #e2e8f0;
  white-space: pre-wrap;
  overflow: auto;
  font-size: 12px;
}

.code-box {
  position: relative;
}

.copy-btn {
  position: absolute;
  top: 16px;
  right: 10px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, #0f172a 85%, #1e293b);
  color: #e2e8f0;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.copy-btn:hover {
  border-color: #64748b;
}

@media (max-width: 980px) {
  .guide {
    grid-template-columns: 1fr;
  }
  .toc {
    border-right: none;
    border-bottom: 1px solid var(--border);
    max-height: 180px;
  }
}
</style>
