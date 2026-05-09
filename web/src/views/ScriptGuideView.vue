<template>
  <div class="guide">
    <header class="topbar">
      <div class="topbar-title">帮助文档</div>
      <div class="tabs" role="tablist" aria-label="帮助文档分区">
        <button
          type="button"
          class="tab"
          :class="{ active: activeTab === 'script' }"
          role="tab"
          :aria-selected="activeTab === 'script'"
          @click="activeTab = 'script'"
        >
          脚本帮助
        </button>
        <button
          type="button"
          class="tab"
          :class="{ active: activeTab === 'capability' }"
          role="tab"
          :aria-selected="activeTab === 'capability'"
          @click="activeTab = 'capability'"
        >
          能力策略说明
        </button>
      </div>
    </header>

    <aside class="toc">
      <div class="toc-title">{{ activeTab === "script" ? "脚本帮助" : "能力策略说明" }}</div>
      <template v-if="activeTab === 'script'">
        <a href="#start" class="toc-link">快速开始</a>
        <a href="#syntax" class="toc-link">基础语法</a>
        <a href="#builtins" class="toc-link">内置能力调用</a>
        <a href="#internal" class="toc-link">内置脚本 load</a>
        <a href="#soc" class="toc-link">SOC 实战模板</a>
        <a href="#editor" class="toc-link">编辑器使用</a>
        <a href="#debug" class="toc-link">调试步骤</a>
        <a href="#assertions" class="toc-link">测试中心断言</a>
        <a href="#faq" class="toc-link">常见问题</a>
      </template>
      <template v-else>
        <a href="#cap-start" class="toc-link">总览</a>
        <a href="#cap-what" class="toc-link">什么是副作用</a>
        <a href="#cap-defaults" class="toc-link">默认行为（为何会被抑制）</a>
        <a href="#cap-policy" class="toc-link">规则 JSON 怎么写</a>
        <a href="#cap-entrypoints" class="toc-link">各层优先级</a>
        <a href="#cap-debug" class="toc-link">临时调试（脚本/节点/试运行）</a>
        <a href="#cap-test" class="toc-link">测试中心（方案/批次）</a>
        <a href="#cap-deploy" class="toc-link">部署（生产等）</a>
        <a href="#cap-faq" class="toc-link">常见问题</a>
      </template>
    </aside>

    <main class="content">
      <!-- Tab 1: existing script guide -->
      <template v-if="activeTab === 'script'">
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

      <section id="assertions" class="card">
        <h2>7) 测试中心断言（assertions）</h2>
        <p class="muted">
          断言对比对象是运行结束时的 <code class="mono">global_ns</code>。方案级 <code class="mono">assertions</code> 与用例行内
          <code class="mono">_expect</code> 会合并执行，结果显示为 <code class="mono">verdict=pass/fail</code>。
        </p>

        <h3>7.1 规则结构（JSON 数组）</h3>
        <div class="code-box">
          <pre class="code mono">{{ sampleAssertShape }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleAssertShape)">复制</button>
        </div>

        <h3>7.2 支持的 op</h3>
        <ul>
          <li><code class="mono">eq</code>/<code class="mono">ne</code>：严格相等/不等</li>
          <li><code class="mono">contains</code>：字符串包含（把值转为字符串）</li>
          <li><code class="mono">regex</code>：正则匹配（字符串）</li>
          <li><code class="mono">json_match</code>：expected 是 actual 的子集（忽略多余字段）</li>
          <li><code class="mono">starlark</code>：执行表达式，读取 <code class="mono">global_ns</code>（可返回 bool 或 <code class="mono">{pass,message}</code>）</li>
        </ul>

        <h3>7.3 案例：json_match（结构子集）</h3>
        <div class="code-box">
          <pre class="code mono">{{ sampleAssertJsonMatch }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleAssertJsonMatch)">复制</button>
        </div>

        <h3>7.4 案例：starlark（数组包含 + 自定义 message）</h3>
        <div class="code-box">
          <pre class="code mono">{{ sampleAssertStarlark }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleAssertStarlark)">复制</button>
        </div>

        <h3>7.5 低门槛：用例行内 _expect</h3>
        <p class="muted">Runner 会剥离 <code class="mono">_expect</code> / <code class="mono">_expect.*</code>，避免注入 global_ns，并自动生成断言规则。</p>
        <div class="code-box">
          <pre class="code mono">{{ sampleRowExpect }}</pre>
          <button type="button" class="copy-btn" @click="copyCode(sampleRowExpect)">复制</button>
        </div>

        <p class="tip">
          更完整的说明与更多案例见仓库文档：<code class="mono">docs/test-center-assertions.md</code>（给研发/运维查阅）。
        </p>
      </section>

      <section id="faq" class="card">
        <h2>8) 常见问题</h2>
        <h3>Q: 报错 “Task script must evaluate to a dict”</h3>
        <p>A: 你的脚本最终返回值不是字典。请确保末尾结果是 <code class="mono">{...}</code>。</p>
        <h3>Q: 函数没提示怎么办？</h3>
        <p>A: 先输入前缀（如 <code class="mono">dict_</code>），或确认该函数在「Python 内置」列表中存在。</p>
        <h3>Q: internal 函数调用报未定义</h3>
        <p>A: 先写正确的 <code class="mono">load("internal://...", "...")</code> 再使用导出名。</p>
      </section>
      </template>

      <!-- Tab 2: side-effect builtins & capability policy -->
      <template v-else>
        <section id="cap-start" class="card">
          <h1>能力策略与副作用说明</h1>
          <p class="muted">
            说明哪些内置函数属于「副作用」、为何在调试/试运行/测试里常被抑制，以及如何通过<strong>规则列表</strong>（各页面的 JSON，技术字段名多为
            <code class="mono">capability_policy</code> 或节点上的 <code class="mono">capability_overrides</code>）做放行（allow）或重定向（redirect）。
          </p>
          <div class="callout tip">
            <strong>界面上的分层名称（对照用）</strong>
            <ul class="muted tight">
              <li><strong>环境能力策略</strong>：环境（Profile）配置，按 debug / shadow / production 分别保存；字段 <code class="mono">system_capability_policy</code>。</li>
              <li><strong>部署附加策略</strong>：创建部署时填写，仅该部署运行生效；请求体字段 <code class="mono">capability_policy</code>。</li>
              <li><strong>本次附加策略</strong>：节点调试、流程试运行、用户脚本调试等折叠区——只影响<strong>当前这一次</strong>请求，不写回流程。</li>
              <li><strong>测试方案 · 默认附加策略</strong> / <strong>测试批次 · 附加策略</strong>：测试中心；批次可覆盖方案默认。</li>
              <li><strong>节点能力策略（仅此节点）</strong>：写在流程节点上，随版本发布；字段 <code class="mono">capability_overrides</code>。</li>
            </ul>
          </div>
          <div class="callout warn">
            <strong>安全边界（重要）</strong>
            <div class="muted">
              用户脚本调试、节点调试、流程试运行、测试中心均属于「临时 / 受控执行」入口：服务端固定为<strong>调试模式</strong>（
              <code class="mono">RunMode.DEBUG</code>），默认抑制副作用类内置函数。真实生产行为须通过<strong>部署</strong>启动。
            </div>
          </div>
        </section>

        <section id="cap-what" class="card">
          <h2>1) 什么是“副作用 builtin”</h2>
          <p>
            “副作用”指调用会对外部系统产生影响，或对系统状态产生持久影响的行为。典型例子：
          </p>
          <ul>
            <li><strong>外部调用</strong>：HTTP 请求、调用集成平台接口（integration）</li>
            <li><strong>写入</strong>：写数据库（db_write）、发布 MQ（mq_publish）</li>
            <li><strong>有风险读取</strong>：某些跨租户/跨环境读取（由策略决定是否需要约束）</li>
          </ul>
          <p class="muted">
            具体哪些 builtin 属于副作用，由后端 builtin 规格字段 <code class="mono">side_effects</code> 标记；只有
            <code class="mono">side_effects != "none"</code> 的 builtin 才会触发能力检查。
          </p>
        </section>

        <section id="cap-defaults" class="card">
          <h2>2) 默认行为：为何你在调试时“调用没生效”</h2>
          <p>
            在临时调试/试运行/测试中心，系统默认会对副作用 builtin 做 <code class="mono">SUPPRESS</code>：
            调用被短路，函数体不会执行，直接返回一个“被抑制时的返回值”（由后端 builtin spec 定义）。
          </p>
          <div class="code-box">
            <pre class="code mono">{{ sampleSuppressedOut }}</pre>
            <button type="button" class="copy-btn" @click="copyCode(sampleSuppressedOut)">复制</button>
          </div>
          <p class="tip">
            你会在输出里看到类似 <code class="mono">_suppressed: true</code> 的标记（不同 builtin 的字段可能略有差异）。
            这是为了让脚本能“可测试地”处理被抑制的情况，而不是静默失败。
          </p>
        </section>

        <section id="cap-policy" class="card">
          <h2>3) 规则 JSON 怎么写（allow / suppress / redirect）</h2>
          <p class="muted">
            一条策略由若干条规则（CapabilityRule）组成。匹配时通常先看 <code class="mono">builtin_name</code>，再看
            <code class="mono">builtin_category</code>，再落到更泛的默认规则。
          </p>

          <h3>3.1 规则结构</h3>
          <div class="code-box">
            <pre class="code mono">{{ sampleRuleShape }}</pre>
            <button type="button" class="copy-btn" @click="copyCode(sampleRuleShape)">复制</button>
          </div>

          <h3>3.2 白名单（ALLOW）示例</h3>
          <div class="code-box">
            <pre class="code mono">{{ sampleRuleAllow }}</pre>
            <button type="button" class="copy-btn" @click="copyCode(sampleRuleAllow)">复制</button>
          </div>

          <h3>3.3 重定向（REDIRECT）示例</h3>
          <p class="muted">
            REDIRECT 不会自动替你“改 URL”，它只是把 <code class="mono">redirect_params</code> 注入到 builtin 调用上下文；
            builtin 实现如需重定向，应在函数体内读取这些参数并执行自定义逻辑。
          </p>
          <div class="code-box">
            <pre class="code mono">{{ sampleRuleRedirect }}</pre>
            <button type="button" class="copy-btn" @click="copyCode(sampleRuleRedirect)">复制</button>
          </div>
        </section>

        <section id="cap-entrypoints" class="card">
          <h2>4) 各层如何叠加（优先级）</h2>
          <p>
            运行时合并顺序（高 → 低）如下；越靠前越先命中匹配：
          </p>
          <ol>
            <li><strong>节点能力策略</strong>：节点字段 <code class="mono">capability_overrides</code>（界面：节点编辑器「节点能力策略」）。</li>
            <li><strong>本次运行附加</strong>：同一次执行里传入的规则列表。技术名在运行选项中为 <code class="mono">deployment_capability_policy</code>，来源包括：创建部署时的「部署附加策略」、试运行的「本次附加策略」、调试与测试请求里的 <code class="mono">capability_policy</code> 等（各入口名称不同，语义相同）。</li>
            <li><strong>环境能力策略</strong>：当前 Profile 下、对应当前 <code class="mono">RunMode</code> 的 <code class="mono">system_capability_policy</code>。</li>
            <li><strong>运行模式内置默认</strong>：进程内与 <code class="mono">RunMode</code> 绑定的兜底规则（调试模式会默认抑制副作用类内置函数）。</li>
          </ol>
          <p class="muted">
            因此：在调试/试运行里展开的「本次附加策略」与创建部署时的「部署附加策略」处于<strong>同一优先级层</strong>，都高于环境能力策略；节点上的策略又高于它们。
          </p>
        </section>

        <section id="cap-debug" class="card">
          <h2>5) 临时调试（用户脚本 / 节点 / 流程试运行）</h2>
          <p>
            上述入口均为临时执行：默认抑制副作用。在对应页面的「本次附加策略」折叠区可追加规则：
          </p>
          <ul>
            <li>添加 <code class="mono">ALLOW</code> 放行某个 builtin（建议仅指向沙箱/测试环境）</li>
            <li>添加 <code class="mono">REDIRECT</code> 并提供 redirect_params，让 builtin 自行实现重定向</li>
          </ul>
          <div class="code-box">
            <pre class="code mono">{{ sampleProbeScript }}</pre>
            <button type="button" class="copy-btn" @click="copyCode(sampleProbeScript)">复制</button>
          </div>
        </section>

        <section id="cap-test" class="card">
          <h2>6) 测试中心（方案 / 批次）</h2>
          <p>
            测试运行固定为调试模式，默认抑制副作用。界面名称：
          </p>
          <ul>
            <li><strong>测试方案 · 默认附加策略</strong>：保存到方案；新建批次未单独配置时继承。</li>
            <li><strong>测试批次 · 附加策略</strong>：仅该批次；覆盖方案默认。</li>
          </ul>
          <p class="muted">
            建议：与沙箱联调相关的通用规则放在方案默认；批次里只做临时加减。
          </p>
        </section>

        <section id="cap-deploy" class="card">
          <h2>7) 部署（生产 / 预发等）</h2>
          <p>
            部署使用所选 <code class="mono">RunMode</code>（如 production / shadow）。创建部署时的「部署附加策略」与节点、环境能力策略、模式默认按第 4 节顺序合并。
          </p>
          <div class="callout tip">
            <strong>最佳实践</strong>
            <div class="muted">
              把“生产安全边界”写在策略里而不是写在脚本里：例如仅允许访问明确白名单域名，或对写入类 builtin 强制 REDIRECT 到网关。
            </div>
          </div>
        </section>

        <section id="cap-faq" class="card">
          <h2>8) 常见问题</h2>
          <h3>Q: 为什么调试时 http_simple_get 返回 status=0？</h3>
          <p class="muted">
            多为命中 suppress 后的占位返回值。调试入口固定为调试模式，integration 等副作用类内置函数默认会被抑制。
            联调沙箱请在「本次附加策略」或节点「节点能力策略」中配置 allow / redirect。
          </p>
          <h3>Q: REDIRECT 会自动替我改 URL 吗？</h3>
          <p class="muted">
            不会。REDIRECT 只是把参数传给 builtin（通过 redirect_params 上下文）。是否重定向、怎么重定向由 builtin 具体实现决定。
          </p>
          <h3>Q: 我能在调试入口切到 production 吗？</h3>
          <p class="muted">
            不能。临时调试入口服务端锁死 DEBUG，这是为了避免误触发真实生产副作用。生产行为请走部署路径。
          </p>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

const activeTab = ref<"script" | "capability">("script");

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

const sampleAssertShape = `[
  { "id": "ok", "op": "eq", "path": "out.ok", "expected": true }
]`;

const sampleAssertJsonMatch = `[
  {
    "id": "payment_subset",
    "op": "json_match",
    "path": "out.payment",
    "expected": { "status": "SUCCESS", "currency": "CNY" }
  }
]`;

const sampleAssertStarlark = `[
  {
    "id": "items_contains_sku",
    "op": "starlark",
    "expr": "{'pass': any([x.get('sku') == 'A001' for x in (global_ns.get('out', {}).get('items') or [])]), 'message': 'missing sku A001'}"
  }
]`;

const sampleRowExpect = `{
  "case_id": "c1",
  "input": 1,
  "_expect.path": "out.result",
  "_expect.equals": 2
}`;

// --------------------------
// Capability / side effects docs samples
// --------------------------

const sampleSuppressedOut = `# 示例：当副作用 builtin 被 SUPPRESS
{
  "status": 0,
  "body": null,
  "_suppressed": true
}`;

const sampleRuleShape = `{
  "builtin_category": "integration",     // 可选：按类目匹配
  "builtin_name": "http_simple_get",     // 可选：按 builtin 精确匹配（优先级更高）
  "action": "suppress|allow|redirect",   // 必填
  "redirect_params": { "url": "..." }    // 仅 redirect 时需要
}`;

const sampleRuleAllow = `[
  { "builtin_name": "http_simple_get", "action": "allow" }
]`;

const sampleRuleRedirect = `[
  {
    "builtin_name": "http_simple_get",
    "action": "redirect",
    "redirect_params": { "url": "https://sandbox.example/api" }
  }
]`;

const sampleProbeScript = `# 任意任务脚本 / 用户脚本里都可以这样写：
r = http_simple_get("https://prod.example/api/ping")
{"probe": r}

# 在临时调试入口默认会被抑制（SUPPRESS），输出里会有 _suppressed=true
# 如需联调沙箱：在页面「本次附加策略」里加 allow 或 redirect`;

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

.topbar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.topbar-title {
  font-weight: 700;
  font-size: 13px;
}

.tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tab {
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  border-radius: 10px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.tab:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--bg) 80%, var(--surface));
}

.tab.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  background: var(--accent-soft);
  font-weight: 600;
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

.callout {
  border-radius: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  margin-top: 10px;
}

.callout.warn {
  background: color-mix(in srgb, #f59e0b 14%, transparent);
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.callout.tip {
  background: color-mix(in srgb, #10b981 10%, transparent);
  border-color: color-mix(in srgb, #10b981 30%, transparent);
}

.callout strong {
  display: block;
  margin-bottom: 6px;
}

ul.tight {
  margin: 6px 0 0;
  padding-left: 1.2em;
}

ul.tight li {
  margin: 4px 0;
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
