from pathlib import Path

p = Path(r"e:\cursor\flow_engine\web\src\views\CapabilityCenterView.vue")
text = p.read_text(encoding="utf-8")

start = "    <!-- 用户脚本 -->\n"
end = "    <DebugDrawer\n"
i0 = text.index(start)
i1 = text.index(end, i0)

new_block = '''    <!-- 用户脚本 -->
    <div v-show="activeSegment === 'user'" class="body body-user">
      <aside class="side user-nav">
        <motion>div class="user-nav-head">
          <span class="user-nav-title">脚本列表</span>
          <button type="button" class="btn ghost sm" @click="openModuleDialog">添加模块</button>
        </div>
        <label class="sr-only" for="user-search">搜索模块或脚本</label>
        <input
          id="user-search"
          v-model="userSearch"
          type="search"
          class="search-inp user-search"
          placeholder="搜索模块、脚本名…"
          autocomplete="off"
        />
        <div class="user-mod-list">
          <div v-for="g in filteredUserGroups" :key="g.module" class="user-mod-block">
            <div class="user-mod-head">
              <span class="user-mod-name mono">{{ g.module }}</span>
              <button type="button" class="btn ghost sm user-mod-add" @click="startNewUserScript(g.module)">
                添加脚本
              </button>
            </div>
            <ul class="user-script-list">
              <li
                v-for="p in g.scripts"
                :key="p"
                class="user-script-item"
                :class="{ active: !userDraftModule && scriptPath === p }"
                role="button"
                tabindex="0"
                @click="selectUserScript(g.module, p)"
                @keydown.enter="selectUserScript(g.module, p)"
              >
                <span class="mono">{{ userScriptFileName(p) }}</span>
              </li>
              <li v-if="!g.scripts.length" class="user-script-empty muted">暂无脚本</li>
            </ul>
          </div>
        </div>
        <p v-if="filteredUserGroups.length === 0" class="empty-hint">无匹配项；请点击「添加模块」。</p>
      </aside>
      <main class="main-detail user-workspace">
        <div v-if="!hasUserWorkspace" class="placeholder user-placeholder">
          <p>从左侧选择脚本，或点击模块行的「添加脚本」。</p>
          <p class="muted">id 格式 <code class="mono">user://模块/名称.star</code></p>
        </div>
        <template v-else>
          <header class="user-ws-head">
            <div class="user-ws-meta-row">
              <span class="user-ws-mode" :data-mode="userIsNew ? 'new' : 'edit'">
                {{ userIsNew ? "新建" : "编辑" }}
              </span>
              <div class="user-ws-field">
                <span class="user-ws-lbl">脚本名</span>
                <div v-if="userIsNew" class="name-suffix-row">
                  <input
                    v-model="newScriptBase"
                    class="inp mono"
                    placeholder="hello"
                    spellcheck="false"
                    autocomplete="off"
                  />
                  <span class="name-suffix mono">.star</span>
                </div>
                <span v-else class="user-ws-val mono">{{ userScriptFileName(scriptPath) }}</span>
              </div>
              <div class="user-ws-field">
                <span class="user-ws-lbl">模块</span>
                <span class="user-ws-val mono">{{ effectiveUserModule }}</span>
              </div>
            </div>
            <button
              type="button"
              class="btn primary"
              :disabled="!canSaveUserScript || saving"
              @click="save"
            >
              {{ saving ? "保存中…" : "保存" }}
            </button>
          </header>
          <p v-if="newScriptError" class="field-err user-ws-err">{{ newScriptError }}</p>
          <p v-else-if="userScriptId" class="user-ws-id mono muted">id: {{ userScriptId }}</p>

          <label class="user-ws-lbl block" for="user-script-desc">描述</label>
          <textarea
            id="user-script-desc"
            v-model="userScriptDescription"
            class="inp user-desc-inp"
            rows="2"
            placeholder="说明此脚本的用途（可选）"
          />

          <section class="user-exports-sec">
            <div class="user-ws-lbl block">导出符号</div>
            <p class="user-exports-hint muted">从 Starlark 源码顶层 <code>def</code> 自动提取，保存时写入</p>
            <div v-if="liveExportFunctions.length" class="user-export-chips">
              <span v-for="ex in liveExportFunctions" :key="ex" class="chip chip-ex">{{ ex }}</span>
            </div>
            <p v-else class="muted user-exports-empty">暂无（在脚本中定义 <code>def</code> 函数）</p>
          </section>

          <section class="script-card script-card--dark script-card-editable user-script-editor">
            <div class="script-sec-head">
              <span class="script-sec-title">Starlark 脚本</span>
            </div>
            <div class="script-body">
              <CodeEditor
                v-model="userScriptContent"
                :read-only="false"
                fill
                appearance="code-dark"
                language="python"
                :registry="registry"
              />
            </div>
          </section>

          <footer class="user-ws-foot">
            <button
              type="button"
              class="btn ghost"
              :disabled="!canDebugUserScript"
              title="调试当前脚本：配置 Profile、抑制规则并执行"
              @click="openUserDebugDrawer"
            >
              调试
            </button>
          </footer>
        </template>
      </main>
    </div>

'''

new_block = new_block.replace('<motion>motion>div class="user-nav-head">', '<div class="user-nav-head">')
new_block = new_block.replace('<motion>motion>div class="user-nav-head">', '<div class="user-nav-head">')
new_block = new_block.replace('<motion>motion>div class="user-nav-head">', '<div class="user-nav-head">')
new_block = new_block.replace('<motion>div class="user-nav-head">', '<div class="user-nav-head">')

text = text[:i0] + new_block + text[i1:]
p.write_text(text, encoding="utf-8")
print("ok")
