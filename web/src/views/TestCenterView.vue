<template>
  <div class="test-page">
    <header class="top">
      <div>
        <div class="title">测试中心</div>
        <div class="subtitle">基于 lookup namespace 驱动的批量回归测试</div>
      </div>
      <div class="head-actions">
        <button type="button" class="btn ghost" @click="newPlan">+ 新建方案</button>
        <div ref="moreWrap" class="menu-wrap" @keydown.esc="closeMoreMenu">
          <button type="button" class="btn ghost" @click="moreOpen = !moreOpen">更多</button>
          <div v-if="moreOpen" class="menu">
            <button type="button" class="menu-item" @click="closeMoreMenu(); newBatch()">临时运行（创建批次）</button>
          </div>
        </div>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="layout">
      <!-- 左侧：方案 & 批次列表 -->
      <aside class="sidebar">
        <div class="side-head">
          <span class="side-title">测试方案</span>
        </div>

        <ul v-if="plans.length" class="batch-list">
          <li
            v-for="p in plans"
            :key="p.id"
            :class="{ active: selectedPlanId === p.id }"
            @click="selectPlan(p.id)"
          >
            <div class="batch-row1">
              <span class="batch-id mono">#P{{ p.id }}</span>
              <span class="spacer" />
              <div class="plan-menu-wrap" @click.stop>
                <button type="button" class="btn ghost small" @click="togglePlanMenu(p.id)">…</button>
                <div v-if="openPlanMenuId === p.id" class="menu">
                  <button type="button" class="menu-item" @click="onCopyPlanFromList(p.id)">复制</button>
                  <button type="button" class="menu-item danger" @click="onDeletePlanFromList(p.id)">删除</button>
                </div>
              </div>
            </div>
            <div class="batch-row2 mono">{{ p.name }}</div>
            <div class="batch-row3">
              <span class="muted small">{{ flowLabelById(p.flow_code) }} · {{ p.version_channel }}</span>
            </div>
          </li>
        </ul>
        <div v-else class="muted small pad center">暂无方案（建议先创建方案）</div>
      </aside>

      <!-- 右侧：详情或表单 -->
      <main class="main">
        <!-- 方案详情 -->
        <section v-if="mode === 'list' && selectedPlanDetail && selectedBatchId == null" class="panel">
          <header class="panel-head">
            <div>
              <div class="panel-title">
                <span class="mono">#P{{ selectedPlanDetail.id }}</span>
                · {{ selectedPlanDetail.name }}
              </div>
              <div class="muted small">
                <span>{{ flowLabelById(selectedPlanDetail.flow_code) }}</span>
                · <span class="mono">{{ selectedPlanDetail.version_channel }}</span>
                · test_ns: <span class="mono">{{ selectedPlanDetail.test_ns_code }}</span>
                · profile: <span class="mono">{{ selectedPlanDetail.profile_code }}</span>
              </div>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <button type="button" class="btn ghost small" @click="refreshSelectedPlan">刷新</button>
              <button type="button" class="btn primary" @click="runSelectedPlan">运行方案</button>
              <button
                v-if="planTab === 'config'"
                type="button"
                class="btn primary"
                :disabled="creating"
                @click="submitPlan"
              >
                {{ creating ? "保存中…" : "保存配置" }}
              </button>
            </div>
          </header>

          <div class="tabs">
            <button type="button" class="tab" :class="{ active: planTab === 'config' }" @click="planTab = 'config'">
              配置
            </button>
            <button type="button" class="tab" :class="{ active: planTab === 'runs' }" @click="planTab = 'runs'">
              批次
            </button>
          </div>

          <div v-if="planTab === 'config'" class="config-wrap">
            <div class="form-grid">
              <label class="field full">
                <span>name <em class="req">*</em></span>
                <input v-model="planForm.name" class="inp" />
              </label>
              <label class="field">
                <span>流程 <em class="req">*</em></span>
                <select v-model="planForm.flow_code" class="inp" disabled>
                  <option :value="planForm.flow_code">{{ flowLabelById(planForm.flow_code) }}</option>
                </select>
              </label>
              <label class="field">
                <span>version_channel <em class="req">*</em></span>
                <select v-model="planForm.version_channel" class="inp" :disabled="!planForm.flow_code">
                  <option value="latest">latest</option>
                  <option value="draft">draft</option>
                  <option v-for="v in versionOptions" :key="v.version" :value="`v${v.version}`">
                    v{{ v.version }}{{ v.description ? ` · ${v.description}` : "" }}
                  </option>
                </select>
              </label>
              <label class="field">
                <span>test_ns_code <em class="req">*</em></span>
                <select v-model="planForm.test_ns_code" class="inp">
                  <option value="">选择测试 lookup namespace</option>
                  <option v-for="ns in lookupNamespaces" :key="ns" :value="ns">{{ ns }}</option>
                </select>
              </label>
              <label class="field">
                <span>profile_code <em class="req">*</em></span>
                <select v-model="planForm.profile_code" class="inp">
                  <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
                </select>
              </label>
              <label class="field">
                <span>concurrency · {{ planForm.concurrency }}</span>
                <input v-model.number="planForm.concurrency" type="range" min="1" max="64" step="1" />
              </label>
            </div>
            <details class="advanced" open>
              <summary>mock_config（方案级，可复用）</summary>
              <div class="mock-list">
                <div v-for="(item, idx) in mockEntries" :key="idx" class="mock-card">
                  <div class="mock-card-head">
                    <select
                      v-model="item.nodeId"
                      class="inp"
                      style="flex: 1; min-width: 0"
                      :disabled="mockNodesLoading"
                    >
                      <option value="">{{ mockNodesLoading ? "加载节点…" : "选择节点…" }}</option>
                      <option v-for="opt in mockNodeSelectOptions" :key="opt.id" :value="opt.id">
                        {{ opt.label }}
                      </option>
                    </select>
                    <select v-model="item.cfg.mode" class="inp" @change="resetCfg(item)">
                      <option value="script">script</option>
                      <option value="fixed">fixed</option>
                      <option value="record_replay">record_replay</option>
                      <option value="fault">fault</option>
                    </select>
                    <InfoTip :text="mockModeInfoText(item.cfg.mode)" wide align-end />
                    <button type="button" class="btn small danger" @click="removeMockEntry(idx)">移除</button>
                  </div>
                  <textarea
                    v-if="item.cfg.mode === 'script'"
                    v-model="item.scriptText"
                    class="ta mono"
                    rows="4"
                    placeholder="Starlark script returning the mock result"
                    spellcheck="false"
                  />
                  <JsonEditor
                    v-else-if="item.cfg.mode === 'fixed'"
                    v-model="item.resultText"
                    :height="120"
                    placeholder='{"output": "..."}'
                  />
                  <div v-else-if="item.cfg.mode === 'record_replay'" class="rr-grid">
                    <label class="field">
                      <span>lookup_ns <em class="req">*</em></span>
                      <input v-model="item.cfg.lookup_ns" class="inp mono" placeholder="ns_code" />
                    </label>
                    <label class="field">
                      <span>profile_code</span>
                      <input v-model="item.cfg.profile_code" class="inp mono" />
                    </label>
                    <label class="field full">
                      <span>key_expr</span>
                      <input v-model="item.cfg.key_expr" class="inp mono" placeholder="ctx.input.id" />
                    </label>
                    <label class="check">
                      <input v-model="item.cfg.record_on_miss" type="checkbox" />
                      <span>未命中时录制</span>
                    </label>
                  </div>
                  <div v-else class="rr-grid">
                    <label class="field">
                      <span>fault_type <em class="req">*</em></span>
                      <select v-model="item.cfg.fault_type" class="inp">
                        <option value="timeout">timeout</option>
                        <option value="exception">exception</option>
                        <option value="dirty_data">dirty_data</option>
                      </select>
                    </label>
                    <label class="field full">
                      <span>fault_params (JSON)</span>
                      <JsonEditor v-model="item.faultParamsText" :height="96" />
                    </label>
                  </div>
                </div>
                <button type="button" class="btn small ghost" @click="addMockEntry">+ 添加节点 mock</button>
              </div>
            </details>

            <details class="advanced">
              <summary>上下文映射（方案级）</summary>
              <ContextMappingEditor v-model="contextMapping" surface="test" style="margin-top: 8px" />
            </details>

          <details class="advanced">
            <summary class="summary-with-tip">
              断言 assertions（JSON 数组）
              <InfoTip
                text="与运行结束时的 global_ns 对比。字段：id、op（eq/ne/contains/regex/json_match/starlark）、path（点路径）、expected；starlark 用 expr，可读 global_ns。测试集行可用 _expect: { path, equals }。"
                wide
                align-end
              />
            </summary>
            <JsonEditor v-model="planForm.assertionsText" :height="200" />
          </details>

          <details class="advanced">
            <summary class="summary-with-tip">
              测试方案 · 默认附加策略
              <span class="badge suppressed-inline" title="测试运行固定为调试模式">调试模式</span>
              <InfoTip
                text="本方案下新建测试批次时，若未单独填写批次策略，则默认附带此处规则。测试运行固定为调试模式，副作用类内置函数默认抑制；此处用于本方案统一的放行或重定向（如沙箱）。"
                wide
                align-end
              />
            </summary>
            <CapabilityRulesEditor v-model="planCapabilityPolicy" />
          </details>
          </div>

          <div v-else>
            <div class="run-toolbar">
              <label class="ctl">
                <span>状态</span>
                <select v-model="planBatchStatusFilter" class="inp" @change="loadPlanBatches">
                  <option value="">全部</option>
                  <option value="running">running</option>
                  <option value="completed">completed</option>
                  <option value="failed">failed</option>
                </select>
              </label>
              <span class="spacer" />
              <button type="button" class="btn ghost small" @click="loadPlanBatches">刷新</button>
              <span class="muted small">共 {{ planBatches?.total ?? 0 }} 条</span>
            </div>

            <table class="grid-table">
              <thead>
                <tr>
                  <th style="width:90px">batch_id</th>
                  <th style="width:110px">状态</th>
                  <th style="width:160px">started_at</th>
                  <th style="width:110px">耗时</th>
                  <th style="width:160px">resolved_ver</th>
                  <th>进度</th>
                  <th style="width:100px">断言通过</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loadingPlanBatches"><td colspan="7" class="muted center">加载中…</td></tr>
                <tr v-else-if="!planBatches || planBatches.batches.length === 0">
                  <td colspan="7" class="muted center">暂无批次记录</td>
                </tr>
                <tr
                  v-for="b in planBatches?.batches ?? []"
                  :key="b.batch_id"
                  @click="selectBatch(b.batch_id)"
                >
                  <td class="mono">#{{ b.plan_batch_no || 0 }}</td>
                  <td><span class="tag" :class="batchStatusTag(b.status)">{{ b.status }}</span></td>
                  <td class="mono small">{{ formatTs(b.started_at) }}</td>
                  <td class="mono small">{{ b.elapsed_ms != null ? `${b.elapsed_ms}ms` : "—" }}</td>
                  <td class="mono small">v{{ b.resolved_ver_no }}</td>
                  <td class="mono small">{{ b.completed_runs }}/{{ b.total_runs }} <span v-if="b.error_runs" class="bad">· {{ b.error_runs }} failed</span></td>
                  <td class="mono small">
                    <span v-if="b.assertion_pass_rate != null">{{ b.assertion_pass_rate }}%</span>
                    <span v-else class="muted">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

        </section>

        <!-- 新建方案表单 -->
        <section v-if="mode === 'plan_create' || mode === 'plan_edit'" class="panel">
          <header class="panel-head">
            <span class="panel-title">{{ mode === 'plan_create' ? "新建方案" : "编辑方案" }}</span>
            <span class="muted small">方案可复用、多次运行；运行会生成独立批次</span>
          </header>
          <div class="form-grid">
            <label class="field full">
              <span>name <em class="req">*</em></span>
              <input v-model="planForm.name" class="inp" placeholder="例如：回归-支付链路-主流程" />
            </label>
            <label class="field">
              <span>流程 <em class="req">*</em></span>
              <select v-model="planForm.flow_code" class="inp" @change="onPlanFlowChange">
                <option value="">选择流程</option>
                <option v-for="f in flowOptions" :key="f.id" :value="f.id">
                  {{ flowListItemLabel(f) }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>version_channel <em class="req">*</em></span>
              <select v-model="planForm.version_channel" class="inp" :disabled="!planForm.flow_code">
                <option value="latest">latest</option>
                <option value="draft">draft</option>
                <option v-for="v in versionOptions" :key="v.version" :value="`v${v.version}`">
                  v{{ v.version }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>test_ns_code <em class="req">*</em></span>
              <select v-model="planForm.test_ns_code" class="inp">
                <option value="">选择测试 lookup namespace</option>
                <option v-for="ns in lookupNamespaces" :key="ns" :value="ns">{{ ns }}</option>
              </select>
            </label>
            <label class="field">
              <span>profile_code <em class="req">*</em></span>
              <select v-model="planForm.profile_code" class="inp">
                <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </label>
            <label class="field">
              <span>concurrency · {{ planForm.concurrency }}</span>
              <input v-model.number="planForm.concurrency" type="range" min="1" max="64" step="1" />
            </label>
          </div>

          <!-- 复用现有 mockEntries/contextMapping 编辑器（与批次一致） -->
          <details class="advanced" open>
            <summary>mock_config（方案级，可复用）</summary>
            <div class="mock-list">
              <div v-for="(item, idx) in mockEntries" :key="idx" class="mock-card">
                <div class="mock-card-head">
                  <select
                    v-model="item.nodeId"
                    class="inp"
                    style="flex: 1; min-width: 0"
                    :disabled="mockNodesLoading"
                  >
                    <option value="">{{ mockNodesLoading ? "加载节点…" : "选择节点…" }}</option>
                    <option v-for="opt in mockNodeSelectOptions" :key="opt.id" :value="opt.id">
                      {{ opt.label }}
                    </option>
                  </select>
                  <select v-model="item.cfg.mode" class="inp" @change="resetCfg(item)">
                    <option value="script">script</option>
                    <option value="fixed">fixed</option>
                    <option value="record_replay">record_replay</option>
                    <option value="fault">fault</option>
                  </select>
                  <InfoTip :text="mockModeInfoText(item.cfg.mode)" wide align-end />
                  <button type="button" class="btn small danger" @click="removeMockEntry(idx)">移除</button>
                </div>
                <textarea
                  v-if="item.cfg.mode === 'script'"
                  v-model="item.scriptText"
                  class="ta mono"
                  rows="4"
                  placeholder="Starlark script returning the mock result"
                  spellcheck="false"
                />
                <JsonEditor
                  v-else-if="item.cfg.mode === 'fixed'"
                  v-model="item.resultText"
                  :height="120"
                  placeholder='{"output": "..."}'
                />
                <div v-else-if="item.cfg.mode === 'record_replay'" class="rr-grid">
                  <label class="field">
                    <span>lookup_ns <em class="req">*</em></span>
                    <input v-model="item.cfg.lookup_ns" class="inp mono" placeholder="ns_code" />
                  </label>
                  <label class="field">
                    <span>profile_code</span>
                    <input v-model="item.cfg.profile_code" class="inp mono" />
                  </label>
                  <label class="field full">
                    <span>key_expr</span>
                    <input v-model="item.cfg.key_expr" class="inp mono" placeholder="ctx.input.id" />
                  </label>
                  <label class="check">
                    <input v-model="item.cfg.record_on_miss" type="checkbox" />
                    <span>未命中时录制</span>
                  </label>
                </div>
                <div v-else class="rr-grid">
                  <label class="field">
                    <span>fault_type <em class="req">*</em></span>
                    <select v-model="item.cfg.fault_type" class="inp">
                      <option value="timeout">timeout</option>
                      <option value="exception">exception</option>
                      <option value="dirty_data">dirty_data</option>
                    </select>
                  </label>
                  <label class="field full">
                    <span>fault_params (JSON)</span>
                    <JsonEditor v-model="item.faultParamsText" :height="96" />
                  </label>
                </div>
              </div>
              <button type="button" class="btn small ghost" @click="addMockEntry">+ 添加节点 mock</button>
            </div>
          </details>

          <details class="advanced">
            <summary>上下文映射（方案级）</summary>
            <ContextMappingEditor v-model="contextMapping" surface="test" style="margin-top: 8px" />
          </details>

          <details class="advanced">
            <summary class="summary-with-tip">
              断言 assertions（JSON 数组）
              <InfoTip
                text="与运行结束时的 global_ns 对比。字段：id、op（eq/ne/contains/regex/json_match/starlark）、path、expected；starlark 用 expr，可读 global_ns。"
                wide
                align-end
              />
            </summary>
            <JsonEditor v-model="planForm.assertionsText" :height="200" />
          </details>

          <details class="advanced">
            <summary class="summary-with-tip">
              测试方案 · 默认附加策略
              <span class="badge suppressed-inline" title="测试运行固定为调试模式">调试模式</span>
              <InfoTip
                text="保存方案时一并保存；新建批次未单独配置时继承。测试固定调试模式，副作用默认抑制；此处为方案级统一的放行或重定向规则。"
                wide
                align-end
              />
            </summary>
            <CapabilityRulesEditor v-model="planCapabilityPolicy" />
          </details>

          <p v-if="formError" class="err">{{ formError }}</p>
          <div class="form-actions">
            <button type="button" class="btn ghost" @click="cancelCreate">取消</button>
            <button type="button" class="btn primary" :disabled="creating" @click="submitPlan">
              {{ creating ? "保存中…" : "保存方案" }}
            </button>
          </div>
        </section>

        <!-- 新建批次表单（临时运行） -->
        <section v-if="mode === 'create'" class="panel">
          <header class="panel-head">
            <span class="panel-title">新建批次</span>
            <span class="muted small">每行 lookup 数据 → 一次调试模式流程试运行（副作用类内置函数默认抑制）</span>
          </header>
          <div class="form-grid">
            <label class="field">
              <span>流程 <em class="req">*</em></span>
              <select v-model="form.flow_code" class="inp" @change="onFlowChange">
                <option value="">选择流程</option>
                <option v-for="f in flowOptions" :key="f.id" :value="f.id">
                  {{ flowListItemLabel(f) }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>ver_no <em class="req">*</em></span>
              <select v-model.number="form.ver_no" class="inp" :disabled="!form.flow_code || form.use_draft">
                <option :value="0">选择版本</option>
                <option v-for="v in versionOptions" :key="v.version" :value="v.version">
                  v{{ v.version }}{{ v.description ? ` · ${v.description}` : "" }}
                </option>
              </select>
            </label>
            <label class="check" style="align-self:end; margin-top:18px;">
              <input v-model="form.use_draft" type="checkbox" :disabled="!form.flow_code" />
              <span>使用草稿（draft）运行</span>
            </label>
            <label class="field">
              <span>test_ns_code <em class="req">*</em></span>
              <select v-model="form.test_ns_code" class="inp">
                <option value="">选择测试 lookup namespace</option>
                <option v-for="ns in lookupNamespaces" :key="ns" :value="ns">{{ ns }}</option>
              </select>
            </label>
            <label class="field">
              <span>profile_code <em class="req">*</em></span>
              <select v-model="form.profile_code" class="inp">
                <option v-for="p in profileOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </label>
            <label class="field">
              <span>concurrency · {{ form.concurrency }}</span>
              <input v-model.number="form.concurrency" type="range" min="1" max="64" step="1" />
            </label>
          </div>

          <details class="advanced">
            <summary>mock_config（节点级 Mock，按 node_id 配置）</summary>
            <div class="mock-list">
              <div v-for="(item, idx) in mockEntries" :key="idx" class="mock-card">
                <div class="mock-card-head">
                  <select
                    v-model="item.nodeId"
                    class="inp"
                    style="flex: 1; min-width: 0"
                    :disabled="mockNodesLoading"
                  >
                    <option value="">{{ mockNodesLoading ? "加载节点…" : "选择节点…" }}</option>
                    <option v-for="opt in mockNodeSelectOptions" :key="opt.id" :value="opt.id">
                      {{ opt.label }}
                    </option>
                  </select>
                  <select v-model="item.cfg.mode" class="inp" @change="resetCfg(item)">
                    <option value="script">script</option>
                    <option value="fixed">fixed</option>
                    <option value="record_replay">record_replay</option>
                    <option value="fault">fault</option>
                  </select>
                  <InfoTip :text="mockModeInfoText(item.cfg.mode)" wide align-end />
                  <button type="button" class="btn small danger" @click="removeMockEntry(idx)">移除</button>
                </div>
                <textarea
                  v-if="item.cfg.mode === 'script'"
                  v-model="item.scriptText"
                  class="ta mono"
                  rows="4"
                  placeholder="Starlark script returning the mock result"
                  spellcheck="false"
                />
                <JsonEditor
                  v-else-if="item.cfg.mode === 'fixed'"
                  v-model="item.resultText"
                  :height="120"
                  placeholder='{"output": "..."}'
                />
                <div v-else-if="item.cfg.mode === 'record_replay'" class="rr-grid">
                  <label class="field">
                    <span>lookup_ns <em class="req">*</em></span>
                    <input v-model="item.cfg.lookup_ns" class="inp mono" placeholder="ns_code" />
                  </label>
                  <label class="field">
                    <span>profile_code</span>
                    <input v-model="item.cfg.profile_code" class="inp mono" />
                  </label>
                  <label class="field full">
                    <span>key_expr</span>
                    <input v-model="item.cfg.key_expr" class="inp mono" placeholder="ctx.input.id" />
                  </label>
                  <label class="check">
                    <input v-model="item.cfg.record_on_miss" type="checkbox" />
                    <span>未命中时录制</span>
                  </label>
                </div>
                <div v-else class="rr-grid">
                  <label class="field">
                    <span>fault_type <em class="req">*</em></span>
                    <select v-model="item.cfg.fault_type" class="inp">
                      <option value="timeout">timeout</option>
                      <option value="exception">exception</option>
                      <option value="dirty_data">dirty_data</option>
                    </select>
                  </label>
                  <label class="field full">
                    <span>fault_params (JSON)</span>
                    <JsonEditor v-model="item.faultParamsText" :height="96" />
                  </label>
                </div>
              </div>
              <button type="button" class="btn small ghost" @click="addMockEntry">+ 添加节点 mock</button>
            </div>
          </details>

          <details class="advanced">
            <summary>上下文映射</summary>
            <p class="muted small" style="margin: 6px 0 0">
              将 lookup 数据集行或消息体映射为流程 <span class="mono">initial_context</span> / <span class="mono">global_ns</span>。
            </p>
            <ContextMappingEditor v-model="contextMapping" surface="test" style="margin-top: 8px" />
          </details>

          <details class="advanced">
            <summary class="summary-with-tip">
              测试批次 · 附加策略
              <span class="badge suppressed-inline" title="测试运行固定为调试模式">调试模式</span>
              <InfoTip
                text="仅本批次生效，优先级高于「测试方案 · 默认附加策略」。空表示本批次不再额外附加（仍受环境能力策略与内置默认约束）。"
                wide
                align-end
              />
            </summary>
            <CapabilityRulesEditor v-model="formCapabilityPolicy" />
          </details>

          <p v-if="formError" class="err">{{ formError }}</p>
          <div class="form-actions">
            <button type="button" class="btn ghost" @click="cancelCreate">取消</button>
            <button type="button" class="btn primary" :disabled="creating" @click="submitBatch">
              {{ creating ? "创建中…" : "创建批次" }}
            </button>
          </div>
        </section>

        <!-- 批次详情 -->
        <section v-else-if="selectedBatch" class="panel">
          <header class="panel-head">
            <div class="panel-head-main">
              <button
                v-if="selectedPlanDetail"
                type="button"
                class="btn ghost small icon-back"
                title="返回批次列表"
                aria-label="返回批次列表"
                @click="backToPlanRuns"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                  <path
                    d="M15 18l-6-6 6-6"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <div class="panel-head-text">
                <div class="panel-title">
                  <span class="mono">#{{ selectedBatch.id }}</span>
                  · {{ flowLabelById(selectedBatch.flow_code) }} v{{ selectedBatch.ver_no }}
                  <span class="tag" :class="batchStatusTag(selectedBatch.status)">{{ selectedBatch.status }}</span>
                </div>
                <div class="muted small">
                  test_ns: <span class="mono">{{ selectedBatch.test_ns_code }}</span>
                  · profile: <span class="mono">{{ selectedBatch.profile_code }}</span>
                  <span v-if="(selectedBatch as any).plan"> · plan: <span class="mono">{{ (selectedBatch as any).plan?.name }}</span></span>
                  <span v-if="selectedBatch.started_at"> · 开始 {{ formatTs(selectedBatch.started_at) }}</span>
                  <span v-if="selectedBatch.finished_at"> · 结束 {{ formatTs(selectedBatch.finished_at) }}</span>
                </div>
              </div>
            </div>
            <div class="panel-head-actions">
              <button type="button" class="btn ghost small" @click="refreshSelected">刷新</button>
            </div>
          </header>

          <div class="progress">
            <div class="progress-info">
              <span
                ><strong class="ok">{{ selectedBatch.completed_runs }}</strong> 通过 ·
                <strong :class="selectedBatch.error_runs ? 'bad' : ''">{{ selectedBatch.error_runs }}</strong> 失败 · 共
                {{ selectedBatch.total_runs }} 条</span
              >
              <span v-if="selectedBatch.total_runs > 0" class="muted small"
                >已结束 {{ progressFinishedPct(selectedBatch) }}%</span
              >
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill ok"
                :style="{
                  width: `${(selectedBatch.completed_runs / Math.max(1, selectedBatch.total_runs)) * 100}%`,
                }"
              />
              <div
                class="progress-fill bad"
                :style="{
                  width: `${(selectedBatch.error_runs / Math.max(1, selectedBatch.total_runs)) * 100}%`,
                }"
              />
            </div>
          </div>

          <details v-if="selectedBatch.summary" class="advanced batch-summary">
            <summary>结果摘要（状态分布 / 断言 / 首批失败）</summary>
            <div class="summary-body muted small">
              <p>
                <span class="mono">by_status</span> {{ JSON.stringify(selectedBatch.summary.by_status) }}
              </p>
              <p>
                <span class="mono">verdict_counts</span>
                {{ JSON.stringify(selectedBatch.summary.verdict_counts) }}
              </p>
              <ul v-if="(selectedBatch.summary.first_failures || []).length" class="fail-list">
                <li v-for="(f, i) in selectedBatch.summary.first_failures" :key="i">
                  <span class="mono">#{{ f.case_index }}</span> {{ f.case_key || "—" }} ·
                  <span class="tag" :class="runStatusTag(f.status)">{{ f.status }}</span>
                  <span v-if="f.verdict" class="tag" :class="verdictTag(f.verdict)">{{ f.verdict }}</span>
                  <span v-if="f.error" class="bad">{{ f.error }}</span>
                </li>
              </ul>
            </div>
          </details>

          <div class="run-toolbar">
            <label class="ctl">
              <span>状态</span>
              <select v-model="runStatusFilter" class="inp" @change="loadBatchRuns">
                <option value="">全部</option>
                <option value="running">running</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
                <option value="terminated">terminated</option>
              </select>
            </label>
            <span class="spacer" />
            <span class="muted small">共 {{ runs?.total ?? 0 }} 条</span>
          </div>

          <table class="grid-table">
            <thead>
              <tr>
                <th style="width:56px">#</th>
                <th style="width:80px">run</th>
                <th style="width:140px">用例键</th>
                <th style="width:72px">断言</th>
                <th style="width:100px">状态</th>
                <th style="width:160px">started_at</th>
                <th style="width:110px">耗时</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingRuns"><td colspan="8" class="muted center">加载中…</td></tr>
              <tr v-else-if="!runs || runs.runs.length === 0">
                <td colspan="8" class="muted center">暂无运行记录</td>
              </tr>
              <tr
                v-for="r in runs?.runs ?? []"
                :key="r.id"
                :class="{ active: selectedRunId === r.id }"
                @click="selectRun(r.id)"
              >
                <td class="mono small">{{ r.batch_run_no ?? r.case_index ?? "—" }}</td>
                <td class="mono">#{{ r.id }}</td>
                <td class="mono small" :title="r.case_key || ''">{{ r.case_key || "—" }}</td>
                <td>
                  <span v-if="r.verdict" class="tag" :class="verdictTag(r.verdict)">{{ r.verdict }}</span>
                  <span v-else class="muted">—</span>
                </td>
                <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
                <td class="mono small">{{ formatTs(r.started_at) }}</td>
                <td class="mono small">{{ runElapsed(r) }}</td>
                <td class="mono small err-cell" :title="r.error || ''">{{ r.error || "—" }}</td>
              </tr>
            </tbody>
          </table>

          <RunDetailDrawer
            :open="selectedRunId != null"
            title="用例运行详情"
            :loading="loadingRunDetail"
            :detail="selectedRunDetail"
            @close="
              selectedRunId = null;
              selectedRunDetail = null;
              loadingRunDetail = false;
            "
          />
        </section>

        <!-- 空状态 -->
        <section v-if="mode === 'list' && !selectedPlanDetail && !selectedBatch" class="panel empty">
          <p class="muted center pad">从左侧选择方案并运行，或选择批次查看结果</p>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import {
  createTestBatch,
  getBatchRun,
  getTestBatch,
  listBatchRuns,
  type CreateTestBatchBody,
  type FaultType,
  type MockConfig,
  type MockMode,
  type TestBatchDetail,
} from "@/api/testBatches";
import type { FlowRunDetail, FlowRunSummary, FlowRunsListResponse } from "@/api/flowRuns";
import { useFlowLabels } from "@/composables/useFlowLabels";
import { fetchDraft, fetchVersion, fetchVersionList, sortFlowVersionsDesc, type FlowVersionMeta } from "@/api/flowVersions";
import { fetchProfileConfig } from "@/api/profiles";
import { fetchLookupList } from "@/api/lookups";
import InfoTip from "@/components/InfoTip.vue";
import JsonEditor from "@/components/JsonEditor.vue";
import RunDetailDrawer from "@/components/RunDetailDrawer.vue";
import CapabilityRulesEditor from "@/components/CapabilityRulesEditor.vue";
import type { CapabilityRule, FlowDocument, FlowNode } from "@/types/flow";
import { displayName as displayNodeName, flowListItemLabel, nodeId as flowNodeLogicalId } from "@/types/flow";
import ContextMappingEditor from "@/components/ContextMappingEditor.vue";
import { DEFAULT_CONTEXT_MAPPING_TEST, type ContextMappingState } from "@/operations/contextMappingConfig";
import {
  createTestPlan,
  copyTestPlan,
  deleteTestPlan,
  getTestPlan,
  listTestPlans,
  listTestPlanBatches,
  patchTestPlan,
  runTestPlan,
  type TestPlanDetail,
  type TestPlanSummary,
  type TestPlanBatchItem,
} from "@/api/testPlans";

type Mode = "list" | "create" | "plan_create" | "plan_edit";
type MockEntry = {
  nodeId: string;
  cfg: MockConfig;
  scriptText: string;
  resultText: string;
  faultParamsText: string;
};

const STORAGE_KEY = "flow_engine.test_center.recent_batches";

function loadRecentIds(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return arr.filter((n) => typeof n === "number");
  } catch {
    // ignore
  }
  return [];
}

function saveRecentIds(ids: number[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids.slice(0, 30)));
  } catch {
    // ignore
  }
}

const error = ref("");
const mode = ref<Mode>("list");
const batches = ref<TestBatchDetail[]>([]);
const recentIds = ref<number[]>(loadRecentIds());
const moreOpen = ref(false);
const moreWrap = ref<HTMLElement | null>(null);

const selectedBatchId = ref<number | null>(null);
const selectedBatch = computed<TestBatchDetail | null>(() =>
  batches.value.find((b) => b.id === selectedBatchId.value) ?? null,
);

// 历史批次入口已下沉到方案 Runs 列表；不再提供左侧“按 batch_id 打开”。

// ---------------- form state ----------------

const { flowOptions, ensureFlowList, flowLabelById } = useFlowLabels();
const versionOptions = ref<FlowVersionMeta[]>([]);
const profileOptions = ref<string[]>([]);
const lookupNamespaces = ref<string[]>([]);

// ---------------- plans state ----------------
const plans = ref<TestPlanSummary[]>([]);
const selectedPlanId = ref<number | null>(null);
const selectedPlanDetail = ref<TestPlanDetail | null>(null);
const planTab = ref<"runs" | "config">("config");
const planBatches = ref<{ total: number; batches: TestPlanBatchItem[] } | null>(null);
const loadingPlanBatches = ref(false);
const planBatchStatusFilter = ref("");
const openPlanMenuId = ref<number | null>(null);

const planForm = reactive<{
  id: number | null;
  name: string;
  flow_code: string;
  version_channel: string;
  test_ns_code: string;
  profile_code: string;
  concurrency: number;
  assertionsText: string;
}>({
  id: null,
  name: "",
  flow_code: "",
  version_channel: "latest",
  test_ns_code: "",
  profile_code: "default",
  concurrency: 4,
  assertionsText: "[]",
});

// CapabilityRule 列表与方案 / 临时批次表单解耦存储 —— reactive 数组难以直接
// 嵌套泛型；分离持有便于 v-model 双向绑定。两个表单不共享，新建/编辑切换会重置。
const planCapabilityPolicy = ref<CapabilityRule[]>([]);
const formCapabilityPolicy = ref<CapabilityRule[]>([]);

const form = reactive<{
  flow_code: string;
  ver_no: number;
  test_ns_code: string;
  profile_code: string;
  concurrency: number;
  use_draft: boolean;
}>({
  flow_code: "",
  ver_no: 0,
  test_ns_code: "",
  profile_code: "default",
  concurrency: 4,
  use_draft: false,
});
const mockEntries = reactive<MockEntry[]>([]);
/** 当前流程版本解析出的节点，用于 mock node 下拉；临时批次与方案表单共用。 */
const mockNodeOptions = ref<Array<{ id: string; label: string }>>([]);
const mockNodesLoading = ref(false);
const creating = ref(false);
const formError = ref("");

const contextMapping = ref<ContextMappingState>({ ...DEFAULT_CONTEXT_MAPPING_TEST });

const mockNodeSelectOptions = computed(() => {
  const base = mockNodeOptions.value;
  const seen = new Set(base.map((x) => x.id));
  const extra: { id: string; label: string }[] = [];
  for (const item of mockEntries) {
    const id = item.nodeId.trim();
    if (id && !seen.has(id)) {
      seen.add(id);
      extra.push({ id, label: `${id}（未在当前版本图中）` });
    }
  }
  return [...base, ...extra];
});

function emptyCfg(m: MockMode): MockConfig {
  if (m === "script") return { mode: "script", script: "" };
  if (m === "fixed") return { mode: "fixed", result: {} };
  if (m === "record_replay")
    return { mode: "record_replay", lookup_ns: "", profile_code: "", key_expr: "", record_on_miss: true };
  return { mode: "fault", fault_type: "timeout", fault_params: {} };
}

function newMockEntry(): MockEntry {
  return {
    nodeId: "",
    cfg: emptyCfg("script"),
    scriptText: "",
    resultText: "{}",
    faultParamsText: "{}",
  };
}

function addMockEntry() {
  mockEntries.push(newMockEntry());
}

function removeMockEntry(idx: number) {
  mockEntries.splice(idx, 1);
}

function resetCfg(entry: MockEntry) {
  entry.cfg = emptyCfg(entry.cfg.mode);
  if (entry.cfg.mode === "script") entry.scriptText = "";
  if (entry.cfg.mode === "fixed") entry.resultText = "{}";
  if (entry.cfg.mode === "fault") entry.faultParamsText = "{}";
}

function walkFlowNodes(nodes: FlowNode[] | undefined, out: FlowNode[]) {
  if (!nodes?.length) return;
  for (const n of nodes) {
    out.push(n);
    if (n.type === "loop" || n.type === "subflow") walkFlowNodes(n.children, out);
  }
}

function nodeChoicesFromDoc(doc: FlowDocument | null | undefined): Array<{ id: string; label: string }> {
  if (!doc?.nodes?.length) return [];
  const flat: FlowNode[] = [];
  walkFlowNodes(doc.nodes, flat);
  return flat
    .map((n) => ({ id: flowNodeLogicalId(n), label: displayNodeName(n) }))
    .filter((x) => x.id);
}

function asFlowDocument(raw: Record<string, unknown>): FlowDocument {
  return raw as unknown as FlowDocument;
}

async function resolvePlanFlowDocument(flowId: string, versionChannel: string): Promise<FlowDocument | null> {
  const ch = (versionChannel || "latest").trim();
  try {
    if (ch === "draft") {
      try {
        return asFlowDocument(await fetchDraft(flowId));
      } catch {
        const vl = await fetchVersionList(flowId);
        if (vl.latest_version > 0) return asFlowDocument(await fetchVersion(flowId, vl.latest_version));
        return null;
      }
    }
    if (ch === "latest") {
      const vl = await fetchVersionList(flowId);
      if (vl.latest_version > 0) return asFlowDocument(await fetchVersion(flowId, vl.latest_version));
      if (vl.has_draft) return asFlowDocument(await fetchDraft(flowId));
      return null;
    }
    const m = /^v?(\d+)$/.exec(ch);
    if (m) return asFlowDocument(await fetchVersion(flowId, parseInt(m[1], 10)));
    const vl = await fetchVersionList(flowId);
    if (vl.latest_version > 0) return asFlowDocument(await fetchVersion(flowId, vl.latest_version));
    return null;
  } catch {
    return null;
  }
}

function shouldLoadPlanMockNodes(): boolean {
  if (mode.value === "plan_create" || mode.value === "plan_edit") return !!planForm.flow_code.trim();
  if (mode.value === "list" && selectedPlanDetail.value && planTab.value === "config") {
    return !!planForm.flow_code.trim();
  }
  return false;
}

async function loadMockNodeOptionsForPlan() {
  mockNodeOptions.value = [];
  const fc = planForm.flow_code.trim();
  if (!fc) return;
  mockNodesLoading.value = true;
  try {
    const doc = await resolvePlanFlowDocument(fc, planForm.version_channel);
    mockNodeOptions.value = nodeChoicesFromDoc(doc);
  } finally {
    mockNodesLoading.value = false;
  }
}

async function loadMockNodeOptionsForBatch() {
  mockNodeOptions.value = [];
  const fc = form.flow_code.trim();
  if (!fc) return;
  mockNodesLoading.value = true;
  try {
    let doc: FlowDocument | null = null;
    if (form.use_draft) {
      try {
        doc = asFlowDocument(await fetchDraft(fc));
      } catch {
        const vl = await fetchVersionList(fc);
        if (vl.latest_version > 0) doc = asFlowDocument(await fetchVersion(fc, vl.latest_version));
      }
    } else if (form.ver_no > 0) {
      doc = asFlowDocument(await fetchVersion(fc, form.ver_no));
    }
    mockNodeOptions.value = nodeChoicesFromDoc(doc);
  } finally {
    mockNodesLoading.value = false;
  }
}

function mockModeInfoText(m: MockMode): string {
  if (m === "script") {
    return "script：用 Starlark 在节点执行前计算返回值（字典），可读 ctx 等运行时对象。适合按上下文拼装结果或轻量分支。例：根据 ctx.input.type 返回不同 output。";
  }
  if (m === "fixed") {
    return 'fixed：直接把 JSON 当作节点输出，不执行脚本。适合稳定桩数据、对照基线。例：{"ok":true,"data":{"id":1}}。';
  }
  if (m === "record_replay") {
    return "record_replay：按 key_expr 在 lookup 命名空间录制/回放上下游结果，首次未命中可写入。适合依赖外部系统时的可重复回归。需配置 lookup_ns，profile 建议与运行环境一致。";
  }
  return "fault：故障注入（timeout / exception / dirty_data），用于验证重试、超时与错误路径。可在 fault_params 中配置延时、异常文案、脏数据形状等。";
}

// ---------------- batch runs state ----------------

const runs = ref<FlowRunsListResponse | null>(null);
const loadingRuns = ref(false);
const runStatusFilter = ref("");
const selectedRunId = ref<number | null>(null);
const selectedRunDetail = ref<FlowRunDetail | null>(null);
const loadingRunDetail = ref(false);

let pollTimer: ReturnType<typeof setInterval> | null = null;
let planBatchesPollTimer: ReturnType<typeof setInterval> | null = null;

function stopPlanBatchesPoll() {
  if (planBatchesPollTimer) {
    clearInterval(planBatchesPollTimer);
    planBatchesPollTimer = null;
  }
}

/** While方案 Runs 列表里仍有 running 批次时，轻量轮询刷新列表。 */
function ensurePlanBatchesPollRunning() {
  stopPlanBatchesPoll();
  if (planTab.value !== "runs" || selectedPlanId.value == null || mode.value !== "list") return;
  if (!planBatches.value?.batches?.some((b) => b.status === "running")) return;
  planBatchesPollTimer = setInterval(async () => {
    if (selectedPlanId.value == null || planTab.value !== "runs") {
      stopPlanBatchesPoll();
      return;
    }
    try {
      const r = await listTestPlanBatches(selectedPlanId.value, {
        status: planBatchStatusFilter.value || undefined,
        offset: 0,
        limit: 50,
      });
      planBatches.value = { total: r.total, batches: r.batches };
    } catch {
      // keep polling on blip
    }
    if (!planBatches.value?.batches?.some((b) => b.status === "running")) {
      stopPlanBatchesPoll();
    }
  }, 3000);
}

function startPolling(batchId: number) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const updated = await getTestBatch(batchId);
      const idx = batches.value.findIndex((b) => b.id === batchId);
      if (idx >= 0) batches.value[idx] = updated;
      else batches.value.unshift(updated);
      if (updated.status !== "running") {
        stopPolling();
      }
      await loadBatchRuns();
    } catch {
      // network blip — keep polling
    }
  }, 3000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function closeMoreMenu() {
  moreOpen.value = false;
}

function onDocPointerDown(e: MouseEvent) {
  const t = e.target as Node | null;
  if (!t) return;

  // top "more" menu
  if (moreOpen.value) {
    const root = moreWrap.value;
    if (root && !root.contains(t)) closeMoreMenu();
  }

  // per-plan menu
  if (openPlanMenuId.value != null) {
    const el = t instanceof Element ? t : null;
    if (!el || !el.closest(".plan-menu-wrap")) {
      openPlanMenuId.value = null;
    }
  }
}

watch(
  () =>
    [
      mode.value,
      planTab.value,
      selectedPlanDetail.value?.id,
      planForm.flow_code,
      planForm.version_channel,
    ] as const,
  () => {
    if (!shouldLoadPlanMockNodes()) return;
    void loadMockNodeOptionsForPlan();
  },
  { immediate: true },
);

watch(
  () => [mode.value, form.flow_code, form.ver_no, form.use_draft] as const,
  () => {
    if (mode.value !== "create") return;
    void loadMockNodeOptionsForBatch();
  },
  { immediate: true },
);

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown, true);
  void ensureFlowList();
});

onUnmounted(() => {
  stopPolling();
  stopPlanBatchesPoll();
  document.removeEventListener("pointerdown", onDocPointerDown, true);
});

// ---------------- actions ----------------

async function refreshPlans() {
  try {
    await ensureFlowList();
    const r = await listTestPlans();
    plans.value = r.plans;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function selectPlan(planId: number) {
  // If we're currently viewing a batch detail, exit that mode first so
  // switching plans always updates the right-side workspace.
  selectedBatchId.value = null;
  selectedRunId.value = null;
  selectedRunDetail.value = null;
  loadingRunDetail.value = false;
  stopPolling();

  // If we're in any creation/editing mode, switch back to list/detail mode.
  mode.value = "list";

  selectedPlanId.value = planId;
  try {
    // Load select options for Config tab editor.
    if (profileOptions.value.length === 0) {
      try {
        const r = await fetchProfileConfig();
        profileOptions.value = r.profiles.length ? r.profiles : ["default"];
      } catch {
        profileOptions.value = ["default"];
      }
    }
    if (lookupNamespaces.value.length === 0) {
      try {
        const r = await fetchLookupList();
        lookupNamespaces.value = r.namespaces;
      } catch {
        // ignore
      }
    }
    try {
      await ensureFlowList();
    } catch {
      // ignore — flowLabelById 将显示「未知流程」
    }

    selectedPlanDetail.value = await getTestPlan(planId);
    // Load version list for this flow so version_channel select is populated.
    try {
      const vr = await fetchVersionList(selectedPlanDetail.value.flow_code);
      versionOptions.value = sortFlowVersionsDesc(vr.versions);
    } catch {
      versionOptions.value = [];
    }
    planTab.value = "config";
    await loadPlanBatches();
    // hydrate editable editors
    loadPlanEditorsFromDetail(selectedPlanDetail.value);
    // 填充编辑表单（但不自动进入编辑模式）
    planForm.id = selectedPlanDetail.value.id;
    planForm.name = selectedPlanDetail.value.name;
    planForm.flow_code = selectedPlanDetail.value.flow_code;
    planForm.version_channel = selectedPlanDetail.value.version_channel;
    planForm.test_ns_code = selectedPlanDetail.value.test_ns_code;
    planForm.profile_code = selectedPlanDetail.value.profile_code;
    planForm.concurrency = selectedPlanDetail.value.concurrency;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function togglePlanMenu(planId: number) {
  openPlanMenuId.value = openPlanMenuId.value === planId ? null : planId;
}

async function onCopyPlanFromList(planId: number) {
  openPlanMenuId.value = null;
  try {
    const created = await copyTestPlan(planId);
    await refreshPlans();
    await selectPlan(created.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function onDeletePlanFromList(planId: number) {
  openPlanMenuId.value = null;
  const ok = window.confirm("确认删除该测试方案吗？（将被归档/软删）");
  if (!ok) return;
  try {
    await deleteTestPlan(planId);
    if (selectedPlanId.value === planId) {
      selectedPlanId.value = null;
      selectedPlanDetail.value = null;
    }
    await refreshPlans();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function refreshSelectedPlan() {
  if (selectedPlanId.value == null) return;
  await selectPlan(selectedPlanId.value);
}

async function loadPlanBatches() {
  if (selectedPlanId.value == null) return;
  loadingPlanBatches.value = true;
  try {
    const r = await listTestPlanBatches(selectedPlanId.value, {
      status: planBatchStatusFilter.value || undefined,
      offset: 0,
      limit: 50,
    });
    planBatches.value = { total: r.total, batches: r.batches };
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingPlanBatches.value = false;
    ensurePlanBatchesPollRunning();
  }
}

function loadPlanEditorsFromDetail(detail: TestPlanDetail) {
  // mockEntries
  mockEntries.splice(0, mockEntries.length);
  for (const [nodeId, cfg] of Object.entries(detail.mock_config || {})) {
    const mode = cfg.mode;
    const entry: any = {
      nodeId,
      cfg: { ...cfg },
      scriptText: "",
      resultText: "{}",
      faultParamsText: "{}",
    };
    if (mode === "script") entry.scriptText = cfg.script ?? "";
    if (mode === "fixed") entry.resultText = JSON.stringify(cfg.result ?? {}, null, 2);
    if (mode === "fault") entry.faultParamsText = JSON.stringify(cfg.fault_params ?? {}, null, 2);
    mockEntries.push(entry);
  }
  contextMapping.value = (detail.context_mapping ?? { mode: "spread" }) as ContextMappingState;
  planForm.assertionsText = JSON.stringify(detail.assertions ?? [], null, 2);
  // capability_policy（计划级默认；空 = 系统 DEBUG 默认 SUPPRESS 所有副作用类）
  planCapabilityPolicy.value = ((detail as any).capability_policy ?? []) as CapabilityRule[];
}

async function selectBatch(id: number) {
  selectedBatchId.value = id;
  mode.value = "list";
  selectedRunId.value = null;
  selectedRunDetail.value = null;
  loadingRunDetail.value = false;
  await refreshSelected();
  await loadBatchRuns();
  if (selectedBatch.value?.status === "running") {
    startPolling(id);
  } else {
    stopPolling();
  }
}

function backToPlanRuns() {
  selectedBatchId.value = null;
  selectedRunId.value = null;
  selectedRunDetail.value = null;
  loadingRunDetail.value = false;
  stopPolling();
  planTab.value = "runs";
  void loadPlanBatches();
}

async function refreshSelected() {
  if (selectedBatchId.value == null) return;
  try {
    const updated = await getTestBatch(selectedBatchId.value);
    const idx = batches.value.findIndex((b) => b.id === updated.id);
    if (idx >= 0) batches.value[idx] = updated;
    else batches.value.unshift(updated);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function loadBatchRuns() {
  if (selectedBatchId.value == null) return;
  loadingRuns.value = true;
  try {
    runs.value = await listBatchRuns(selectedBatchId.value, {
      status: runStatusFilter.value || undefined,
      offset: 0,
      limit: 100,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRuns.value = false;
  }
}

async function selectRun(runId: number) {
  if (selectedBatchId.value == null) return;
  selectedRunId.value = runId;
  loadingRunDetail.value = true;
  selectedRunDetail.value = null;
  try {
    selectedRunDetail.value = await getBatchRun(selectedBatchId.value, runId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRunDetail.value = false;
  }
}

async function newBatch() {
  mode.value = "create";
  selectedBatchId.value = null;
  selectedPlanId.value = null;
  selectedPlanDetail.value = null;
  stopPolling();
  formError.value = "";
  formCapabilityPolicy.value = [];
  try {
    await ensureFlowList();
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
  if (profileOptions.value.length === 0) {
    try {
      const r = await fetchProfileConfig();
      profileOptions.value = r.profiles.length ? r.profiles : ["default"];
      form.profile_code = r.default_profile || profileOptions.value[0] || "default";
    } catch {
      profileOptions.value = ["default"];
    }
  }
  if (lookupNamespaces.value.length === 0) {
    try {
      const r = await fetchLookupList();
      lookupNamespaces.value = r.namespaces;
    } catch {
      // best effort
    }
  }
}

async function newPlan() {
  mode.value = "plan_create";
  selectedBatchId.value = null;
  selectedPlanId.value = null;
  selectedPlanDetail.value = null;
  stopPolling();
  formError.value = "";
  try {
    await ensureFlowList();
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
  if (profileOptions.value.length === 0) {
    try {
      const r = await fetchProfileConfig();
      profileOptions.value = r.profiles.length ? r.profiles : ["default"];
    } catch {
      profileOptions.value = ["default"];
    }
  }
  if (lookupNamespaces.value.length === 0) {
    try {
      const r = await fetchLookupList();
      lookupNamespaces.value = r.namespaces;
    } catch {
      // ignore
    }
  }
  // reset form
  planForm.id = null;
  planForm.name = "";
  planForm.flow_code = "";
  planForm.version_channel = "latest";
  planForm.test_ns_code = "";
  planForm.profile_code = profileOptions.value[0] || "default";
  planForm.concurrency = 4;
  planForm.assertionsText = "[]";
  mockEntries.splice(0, mockEntries.length);
  contextMapping.value = { ...DEFAULT_CONTEXT_MAPPING_TEST };
  planCapabilityPolicy.value = [];
}

function cancelCreate() {
  mode.value = "list";
}

async function onFlowChange() {
  versionOptions.value = [];
  form.ver_no = 0;
  form.use_draft = false;
  if (!form.flow_code) return;
  try {
    const r = await fetchVersionList(form.flow_code);
    versionOptions.value = sortFlowVersionsDesc(r.versions);
    if (versionOptions.value.length > 0) form.ver_no = versionOptions.value[0]!.version;
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
}

async function onPlanFlowChange() {
  versionOptions.value = [];
  if (!planForm.flow_code) return;
  try {
    const r = await fetchVersionList(planForm.flow_code);
    versionOptions.value = sortFlowVersionsDesc(r.versions);
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
}

async function submitPlan() {
  formError.value = "";
  if (!planForm.name.trim()) return void (formError.value = "请填写方案名称");
  if (!planForm.flow_code) return void (formError.value = "请选择流程");
  if (!planForm.test_ns_code) return void (formError.value = "请选择 test_ns_code");
  if (!planForm.profile_code) return void (formError.value = "请选择 profile_code");
  const mockResult = buildMockConfig();
  if (!mockResult.ok) return void (formError.value = mockResult.err);
  let assertions: Array<Record<string, unknown>> = [];
  try {
    const raw = JSON.parse(planForm.assertionsText || "[]");
    if (!Array.isArray(raw)) throw new Error("assertions 必须是 JSON 数组");
    assertions = raw as Array<Record<string, unknown>>;
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
    return;
  }

  creating.value = true;
  // ``capability_policy`` 为方案级默认；批次创建时若未显式覆盖则继承该值。
  // 与 mock_config / context_mapping 一样属于"方案模板"语义。
  const planCapPolicy = planCapabilityPolicy.value as unknown as Array<Record<string, unknown>>;
  try {
    if (planForm.id == null) {
      await createTestPlan({
        name: planForm.name,
        flow_code: planForm.flow_code,
        version_channel: planForm.version_channel,
        test_ns_code: planForm.test_ns_code,
        profile_code: planForm.profile_code,
        concurrency: planForm.concurrency,
        mock_config: mockResult.data,
        context_mapping: contextMapping.value,
        assertions,
        capability_policy: planCapPolicy,
      });
    } else {
      await patchTestPlan(planForm.id, {
        name: planForm.name,
        flow_code: planForm.flow_code,
        version_channel: planForm.version_channel,
        test_ns_code: planForm.test_ns_code,
        profile_code: planForm.profile_code,
        concurrency: planForm.concurrency,
        mock_config: mockResult.data,
        context_mapping: contextMapping.value,
        assertions,
        capability_policy: planCapPolicy,
      });
    }
    await refreshPlans();
    mode.value = "list";
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  } finally {
    creating.value = false;
  }
}

async function runSelectedPlan() {
  if (selectedPlanId.value == null) return;
  try {
    const res = await runTestPlan(selectedPlanId.value);
    recentIds.value = [res.batch_id, ...recentIds.value.filter((x) => x !== res.batch_id)];
    saveRecentIds(recentIds.value);
    planTab.value = "runs";
    await selectBatch(res.batch_id);
    void loadPlanBatches();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function buildMockConfig(): { ok: true; data: Record<string, MockConfig> } | { ok: false; err: string } {
  const out: Record<string, MockConfig> = {};
  for (const item of mockEntries) {
    const nid = item.nodeId.trim();
    if (!nid) return { ok: false, err: "mock 配置必须填写 node_id" };
    const cfg = { ...item.cfg };
    if (cfg.mode === "script") {
      cfg.script = item.scriptText;
      if (!cfg.script) return { ok: false, err: `node ${nid}: script 模式必须填写脚本` };
    } else if (cfg.mode === "fixed") {
      try {
        cfg.result = JSON.parse(item.resultText || "null");
      } catch (e) {
        return { ok: false, err: `node ${nid}: result JSON 解析失败 — ${e instanceof Error ? e.message : String(e)}` };
      }
      if (cfg.result === null || cfg.result === undefined) {
        return { ok: false, err: `node ${nid}: fixed 模式必须提供 result` };
      }
    } else if (cfg.mode === "record_replay") {
      if (!cfg.lookup_ns) return { ok: false, err: `node ${nid}: record_replay 需要 lookup_ns` };
    } else if (cfg.mode === "fault") {
      try {
        cfg.fault_params = JSON.parse(item.faultParamsText || "{}");
      } catch (e) {
        return { ok: false, err: `node ${nid}: fault_params JSON 解析失败 — ${e instanceof Error ? e.message : String(e)}` };
      }
      if (!cfg.fault_type) return { ok: false, err: `node ${nid}: fault 模式必须选择 fault_type` };
      cfg.fault_type = cfg.fault_type as FaultType;
    }
    out[nid] = cfg;
  }
  return { ok: true, data: out };
}

async function submitBatch() {
  formError.value = "";
  if (!form.flow_code) {
    formError.value = "请选择流程";
    return;
  }
  if (!form.use_draft && !form.ver_no) {
    formError.value = "请选择 ver_no";
    return;
  }
  if (!form.test_ns_code) {
    formError.value = "请选择 test_ns_code";
    return;
  }
  if (!form.profile_code) {
    formError.value = "请选择 profile_code";
    return;
  }
  const mockResult = buildMockConfig();
  if (!mockResult.ok) {
    formError.value = mockResult.err;
    return;
  }
  const body: CreateTestBatchBody = {
    flow_code: form.flow_code,
    ...(form.use_draft ? { version_channel: "draft" } : { ver_no: form.ver_no }),
    test_ns_code: form.test_ns_code,
    profile_code: form.profile_code,
    concurrency: form.concurrency,
    mock_config: mockResult.data,
    context_mapping: contextMapping.value,
    // 批次级 capability_policy；空数组 = 测试中心系统默认（DEBUG → 全部 SUPPRESS）。
    capability_policy: formCapabilityPolicy.value as unknown as Array<Record<string, unknown>>,
  };
  creating.value = true;
  try {
    const res = await createTestBatch(body);
    recentIds.value = [res.batch_id, ...recentIds.value.filter((x) => x !== res.batch_id)];
    saveRecentIds(recentIds.value);
    await selectBatch(res.batch_id);
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  } finally {
    creating.value = false;
  }
}

// ---------------- helpers ----------------

function batchStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  return "info";
}

function runStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "terminated") return "warn";
  return "info";
}

function verdictTag(verdict: string | null | undefined): string {
  if (verdict === "pass") return "ok";
  if (verdict === "fail") return "bad";
  return "info";
}

function formatTs(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

/** Share of cases that have finished (pass or fail); counters are mutually exclusive per case. */
function progressFinishedPct(b: TestBatchDetail): number {
  if (b.total_runs <= 0) return 0;
  return Math.round(((b.completed_runs + b.error_runs) / b.total_runs) * 100);
}

function runElapsed(r: FlowRunSummary): string {
  if (!r.started_at) return "—";
  const start = Date.parse(r.started_at);
  if (Number.isNaN(start)) return "—";
  const end = r.finished_at ? Date.parse(r.finished_at) : Date.now();
  if (Number.isNaN(end)) return "—";
  const diff = end - start;
  if (diff < 0) return "—";
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60_000) return `${(diff / 1000).toFixed(2)}s`;
  return `${(diff / 60_000).toFixed(1)}min`;
}

watch(
  () => selectedBatch.value?.status,
  (s) => {
    if (s === "running" && selectedBatchId.value != null) startPolling(selectedBatchId.value);
    else stopPolling();
  },
);

watch(planTab, (t) => {
  if (t !== "runs") {
    stopPlanBatchesPoll();
    return;
  }
  if (selectedPlanId.value != null && mode.value === "list") {
    void loadPlanBatches();
  }
});

void refreshPlans();
</script>

<style scoped>
.test-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.title {
  font-size: 16px;
  font-weight: 700;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
}

.head-actions {
  display: flex;
  gap: 8px;
}

.menu-wrap {
  position: relative;
}

.plan-menu-wrap {
  position: relative;
}

.plan-menu-wrap .menu {
  right: 0;
  top: calc(100% + 6px);
  z-index: 30;
}

.menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 180px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 6px;
  z-index: 20;
}

.menu-item {
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  cursor: pointer;
}

.menu-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.menu-item.danger {
  color: #b91c1c;
}

.menu-item.danger:hover {
  background: color-mix(in srgb, #ef4444 12%, transparent);
}

.tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}

.tab {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--muted);
}

.tab.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  font-weight: 600;
}

.inp.readonly {
  background: #fbfdff;
}

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 12px;
}

.sidebar {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.side-title {
  font-weight: 700;
  font-size: 12px;
}

.open-by-id {
  display: flex;
  gap: 6px;
}

.batch-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.batch-list li {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfdff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.batch-list li:hover {
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.batch-list li.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.batch-row1 {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.batch-id {
  font-weight: 700;
}

.batch-row2 {
  font-size: 11px;
  color: var(--text);
}

.batch-row3 {
  display: flex;
  gap: 6px;
}

.main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel.empty {
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-head-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.panel-head-text {
  min-width: 0;
}

.panel-head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.btn.icon-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 6px;
  line-height: 0;
  color: var(--muted);
}

.btn.icon-back:hover {
  color: var(--text);
}

.panel-title {
  font-weight: 700;
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}

.field.full {
  grid-column: 1 / -1;
}

.req {
  color: #e11d48;
  font-style: normal;
  margin-left: 2px;
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 9px;
  background: #fff;
  font-size: 12px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.btn.small {
  padding: 4px 8px;
  font-size: 11px;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}

.btn.danger {
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 30%, transparent);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.advanced {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: #fbfdff;
}

.advanced summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
}

.summary-with-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.badge.suppressed-inline {
  display: inline-flex;
  align-items: center;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 999px;
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
}

.batch-summary {
  margin-top: 10px;
}

.summary-body {
  margin-top: 8px;
}

.fail-list {
  margin: 8px 0 0;
  padding-left: 18px;
}

.fail-list li {
  margin: 4px 0;
}

.mock-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.mock-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mock-card-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.ta {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  font-size: 11px;
  resize: vertical;
}

.rr-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.progress {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfdff;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-info {
  display: flex;
  gap: 12px;
  align-items: baseline;
  font-size: 12px;
}

.progress-bar {
  display: flex;
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.progress-fill {
  transition: width 0.3s ease;
}

.progress-fill.ok {
  background: linear-gradient(180deg, #34d399, #10b981);
}

.progress-fill.bad {
  background: linear-gradient(180deg, #f87171, #ef4444);
}

.run-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.spacer { flex: 1; }

.ctl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

.grid-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface);
}

.grid-table th,
.grid-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 12px;
  vertical-align: middle;
}

.grid-table th {
  background: #fbfdff;
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
}

.grid-table tbody tr {
  cursor: pointer;
}

.grid-table tbody tr:hover {
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
}

.grid-table tbody tr.active {
  background: var(--accent-soft);
}

.grid-table tbody tr:last-child td {
  border-bottom: none;
}

.tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.tag.ok { background: color-mix(in srgb, #10b981 14%, transparent); color: #047857; border-color: color-mix(in srgb, #10b981 35%, transparent); }
.tag.bad { background: color-mix(in srgb, #ef4444 14%, transparent); color: #b91c1c; border-color: color-mix(in srgb, #ef4444 35%, transparent); }
.tag.warn { background: color-mix(in srgb, #f59e0b 18%, transparent); color: #92400e; border-color: color-mix(in srgb, #f59e0b 35%, transparent); }
.tag.running { background: color-mix(in srgb, #3b82f6 14%, transparent); color: #1d4ed8; border-color: color-mix(in srgb, #3b82f6 35%, transparent); }

.muted {
  color: var(--muted);
}

.bad {
  color: #b91c1c;
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.pad {
  padding: 16px 12px;
  margin: 0;
}

.err-cell {
  color: #b91c1c;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: var(--mono);
}
</style>
