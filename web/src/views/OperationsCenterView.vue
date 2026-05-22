<template>
  <div class="ops-page">
    <header class="top">
      <div>
        <div class="title">运行中心</div>
        <div class="subtitle">部署管理 · 运行实例 · 工作节点状态</div>
      </div>
      <button type="button" class="btn ghost" @click="reloadActive">刷新</button>
    </header>

    <nav class="tabs" role="tablist">
      <button
        v-for="t in TABS"
        :key="t.id"
        role="tab"
        :aria-selected="tab === t.id"
        :class="['tab', { active: tab === t.id }]"
        type="button"
        @click="switchTab(t.id)"
      >
        {{ t.label }}
      </button>
    </nav>

    <p v-if="notice" class="notice">{{ notice }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <!-- confirm modal (unified pattern) -->
    <div v-if="confirmOpen" class="confirm-mask" @click.self="closeConfirm">
      <div class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="confirmTitle">
        <div class="confirm-title">{{ confirmTitle }}</div>
        <p class="confirm-text">{{ confirmText }}</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" :disabled="confirmBusy" @click="closeConfirm">取消</button>
          <button type="button" class="btn danger" :disabled="confirmBusy" @click="confirmExecute">
            {{ confirmBusy ? "处理中…" : confirmCta }}
          </button>
        </div>
      </div>
    </div>

    <!-- ===================== 部署管理 ===================== -->
    <section v-if="tab === 'deployments'" class="tab-body tab-body--fill">
      <div class="dep2-layout">
        <!-- 左侧：部署导航列表 -->
        <aside class="dep2-sidebar">
          <header class="dep2-sidehead">
            <div>
              <div class="dep2-title">部署管理</div>
              <div class="muted small">共 {{ deployments.length }} 条</div>
            </div>
            <div class="dep2-nav">
              <button type="button" class="seg" :class="{ active: depWorkspace === 'overview' }" @click="openDeployOverview()">概览</button>
              <button type="button" class="seg" :class="{ active: depWorkspace === 'create' }" @click="openCreateForm()">新建</button>
            </div>
          </header>

          <div class="dep2-filters">
            <div class="dep2-filterbar">
              <input v-model="depFilters.flow_code" class="inp dep2-search" placeholder="搜索流程名称" />
              <button type="button" class="btn small ghost" :disabled="loadingDep" @click="loadDeployments">查询</button>
              <button
                type="button"
                class="btn small ghost"
                :disabled="loadingDep && deployments.length === 0"
                @click="
                  depFilters.flow_code = '';
                  depFilters.status = '';
                  depFilters.mode = '';
                  loadDeployments();
                "
              >重置</button>
            </div>

            <div class="dep2-filter-rows">
              <div class="dep2-filter-row">
                <span class="muted small dep2-filter-label">状态</span>
                <div class="seg-tabs compact dep2-filter-scroll" style="border:none; padding:0;">
                  <button type="button" class="seg" :class="{ active: depFilters.status === '' }" :title="`全部 ${deployments.length}`" @click="depFilters.status=''; loadDeployments()">全部</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'running' }" :title="`running ${depCount.running}`" @click="depFilters.status='running'; loadDeployments()">running</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'pending' }" :title="`pending ${depCount.pending}`" @click="depFilters.status='pending'; loadDeployments()">pending</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'stopping' }" :title="`stopping ${depCount.stopping}`" @click="depFilters.status='stopping'; loadDeployments()">stopping</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'stopped' }" :title="`stopped ${depCount.stopped}`" @click="depFilters.status='stopped'; loadDeployments()">stopped</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'failed' }" :title="`failed ${depCount.failed}`" @click="depFilters.status='failed'; loadDeployments()">failed</button>
                </div>
              </div>

              <div class="dep2-filter-row">
                <span class="muted small dep2-filter-label">模式</span>
                <div class="seg-tabs compact dep2-filter-scroll" style="border:none; padding:0;">
                  <button type="button" class="seg" :class="{ active: depFilters.mode === '' }" @click="depFilters.mode=''; loadDeployments()">全部</button>
                  <button type="button" class="seg" :class="{ active: depFilters.mode === 'production' }" @click="depFilters.mode='production'; loadDeployments()">production</button>
                  <button type="button" class="seg" :class="{ active: depFilters.mode === 'shadow' }" @click="depFilters.mode='shadow'; loadDeployments()">shadow</button>
                </div>
              </div>
            </div>
          </div>

          <ul class="dep2-list" role="listbox" aria-label="deployments">
            <li v-if="loadingDep" class="muted small pad center">加载中…</li>
            <li v-else-if="filteredDeployments.length === 0" class="muted small pad center">
              {{ deployments.length === 0 ? "暂无部署，建议先创建一个 production/shadow 部署" : "无匹配的部署" }}
            </li>
            <li
              v-for="d in filteredDeployments"
              :key="d.id"
              class="dep2-item"
              :class="{ active: selectedDeploymentId === d.id }"
              role="option"
              :aria-selected="selectedDeploymentId === d.id"
              @click="selectDeployment(d.id)"
            >
              <div class="dep2-row1">
                <span class="mono dep2-id">#{{ d.id }}</span>
                <span class="spacer" />
                <span class="tag" :class="statusTag(d.status)">{{ d.status }}</span>
                <span class="tag mode">{{ d.mode }}</span>
                <div class="dep2-menu-wrap" @click.stop>
                  <button type="button" class="icon-btn" aria-label="更多" title="更多" @click="toggleDepMenu(d.id)">…</button>
                  <div v-if="openDepMenuId === d.id" class="menu">
                    <button
                      type="button"
                      class="menu-item"
                      @click="
                        closeDepMenu();
                        copyText(
                          JSON.stringify(
                            {
                              id: d.id,
                              flow_code: d.flow_code,
                              ver_no: d.ver_no,
                              mode: d.mode,
                              schedule_type: d.schedule_type,
                              cron_expr: d.schedule_type === 'cron' ? d.schedule_config?.cron_expr : undefined,
                              status: d.status,
                              env_profile_code: d.env_profile_code || '',
                              updated_at: d.updated_at,
                              created_at: d.created_at,
                            },
                            null,
                            2,
                          ),
                        );
                      "
                    >复制</button>
                    <button type="button" class="menu-item danger" @click="closeDepMenu(); removeDeployment(d.id)">删除</button>
                  </div>
                </div>
              </div>
              <div class="dep2-row2">
                <div class="dep2-flow">{{ flowLabelById(d.flow_code) }}</div>
                <div class="muted small">v{{ d.ver_no }} · {{ d.schedule_type }}<span v-if="d.schedule_type === 'cron' && d.schedule_config?.cron_expr" class="mono"> · {{ d.schedule_config.cron_expr }}</span></div>
              </div>
              <div class="dep2-row3 muted small">
                <span class="mono">{{ d.env_profile_code || "—" }}</span>
                <span class="spacer" />
                <span class="mono">{{ formatTs(d.updated_at || d.created_at) }}</span>
              </div>
            </li>
          </ul>
        </aside>

        <!-- 右侧：部署工作台 -->
        <main class="dep2-main">
          <section v-if="depWorkspace === 'overview'" class="panel">
            <header class="panel-head">
              <div>
                <div class="panel-title">运行中心概览</div>
                <div class="muted small">在左侧选择部署进行管理，或点击“新建”创建部署</div>
              </div>
              <div class="panel-actions">
                <button type="button" class="btn small ghost" @click="loadDeployments">刷新部署</button>
                <button type="button" class="btn small ghost" @click="loadWorkers">刷新节点</button>
                <button type="button" class="btn small ghost" @click="loadRuns">刷新运行</button>
              </div>
            </header>

            <div class="overview-grid">
              <article class="ov-card">
                <div class="ov-title">部署</div>
                <div class="ov-metrics">
                  <div class="ov-metric"><div class="ov-num mono">{{ deployments.length }}</div><div class="ov-label">全部</div></div>
                  <div class="ov-metric"><div class="ov-num mono">{{ depCount.running }}</div><div class="ov-label">running</div></div>
                  <div class="ov-metric"><div class="ov-num mono">{{ depCount.pending }}</div><div class="ov-label">pending</div></div>
                  <div class="ov-metric"><div class="ov-num mono" :class="{ bad: depCount.failed > 0 }">{{ depCount.failed }}</div><div class="ov-label">failed</div></div>
                </div>
                <div class="ov-actions">
                  <button type="button" class="btn primary" @click="openCreateForm">+ 新建部署</button>
                </div>
              </article>

              <article class="ov-card">
                <div class="ov-title">工作节点</div>
                <div class="ov-metrics">
                  <div class="ov-metric"><div class="ov-num mono">{{ workers.length }}</div><div class="ov-label">全部</div></div>
                  <div class="ov-metric"><div class="ov-num mono">{{ workerCount.active }}</div><div class="ov-label">active</div></div>
                  <div class="ov-metric"><div class="ov-num mono">{{ workerCount.idle }}</div><div class="ov-label">idle</div></div>
                  <div class="ov-metric"><div class="ov-num mono">{{ workerCount.dead }}</div><div class="ov-label">dead</div></div>
                </div>
                <div class="ov-actions">
                  <button type="button" class="btn primary" @click="switchTab('workers')">查看节点</button>
                </div>
              </article>

              <article class="ov-card">
                <div class="ov-title">最近运行</div>
                <div class="ov-table-wrap">
                  <table class="grid-table mini">
                    <thead>
                      <tr>
                        <th style="width:80px">run</th>
                        <th>flow</th>
                        <th style="width:110px">状态</th>
                        <th style="width:120px">耗时</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="loadingRuns"><td colspan="4" class="muted center">加载中…</td></tr>
                      <tr v-else-if="!runsResp || runsResp.runs.length === 0"><td colspan="4" class="muted center">暂无运行记录</td></tr>
                      <tr v-for="r in (runsResp?.runs ?? []).slice(0, 6)" :key="r.id" @click="selectRun(r.id); switchTab('runs')">
                        <td class="mono">#{{ r.id }}</td>
                        <td><div>{{ flowLabelById(r.flow_code) }}</div><div class="muted small">v{{ r.ver_no }}</div></td>
                        <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
                        <td class="mono small">{{ runElapsed(r) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="ov-actions">
                  <button type="button" class="btn primary" @click="switchTab('runs')">打开运行实例</button>
                </div>
              </article>
            </div>
          </section>

          <DeploymentCreateForm
            v-if="creatingDeployment || depWorkspace === 'create'"
            ref="deployCreateFormRef"
            :flow-options="flowOptions"
            :profile-options="profileOptions"
            :workers="workers"
            :active-workers="activeWorkers"
            :worker-status-class="workerStatusClass"
            @cancel="openDeployOverview()"
            @created="onDeploymentCreated"
          />

          <!-- 部署详情工作台 -->
          <section v-else-if="selectedDeployment && depWorkspace === 'detail'" class="panel">
            <header class="panel-head">
              <div>
                <div class="panel-title">
                  <span class="mono">#{{ selectedDeployment.id }}</span>
                  · <span>{{ flowLabelById(selectedDeployment.flow_code) }}</span>
                  · v{{ selectedDeployment.ver_no }}
                  <span class="tag mode">{{ selectedDeployment.mode }}</span>
                  <span class="tag" :class="statusTag(selectedDeployment.status)">{{ selectedDeployment.status }}</span>
                </div>
                <div class="muted small">
                  schedule <span class="mono">{{ selectedDeployment.schedule_type }}</span>
                  <span v-if="selectedDeployment.schedule_type === 'cron' && selectedDeployment.schedule_config?.cron_expr">
                    · <span class="mono">{{ selectedDeployment.schedule_config.cron_expr }}</span>
                  </span>
                  · profile <span class="mono">{{ selectedDeployment.env_profile_code || "—" }}</span>
                  <span v-if="selectedDeployment.updated_at"> · updated <span class="mono">{{ formatTs(selectedDeployment.updated_at) }}</span></span>
                </div>
              </div>
              <div class="panel-actions">
                <button type="button" class="btn ghost small" @click="selectDeployment(selectedDeployment.id)">刷新</button>
                <button
                  v-if="selectedDeployment.status === 'running'"
                  type="button"
                  class="btn warn"
                  @click="requestStopDeployment(selectedDeployment.id)"
                >停止</button>
                <button
                  v-else-if="selectedDeployment.status === 'stopped'"
                  type="button"
                  class="btn primary"
                  @click="requestStartDeployment(selectedDeployment.id)"
                >启动</button>
                <button
                  v-else-if="selectedDeployment.status === 'stopping' || selectedDeployment.status === 'failed'"
                  type="button"
                  class="btn"
                  @click="requestRestartDeployment(selectedDeployment.id)"
                >重启</button>
              </div>
            </header>

            <nav class="seg-tabs" aria-label="deployment detail tabs">
              <button type="button" class="seg" :class="{ active: depDetailTab === 'overview' }" @click="depDetailTab = 'overview'">概览</button>
              <button
                v-if="selectedDeployment.schedule_type === 'subscription'"
                type="button"
                class="seg"
                :class="{ active: depDetailTab === 'messages' }"
                @click="depDetailTab = 'messages'; depMessagesOffset = 0; loadSubscriptionMessages()"
              >消费</button>
              <button type="button" class="seg" :class="{ active: depDetailTab === 'runs' }" @click="depDetailTab = 'runs'; depRunsOffset=0; loadEmbeddedDepRuns()">运行</button>
              <button type="button" class="seg" :class="{ active: depDetailTab === 'config' }" @click="depDetailTab = 'config'">配置</button>
              <button type="button" class="seg jump" @click="viewRuns(selectedDeployment, { forceGlobal: true })">
                全局运行页 <span class="jump-ico" aria-hidden="true">↗</span>
              </button>
            </nav>

            <section v-if="depDetailTab === 'overview'" class="panel-body">
              <div class="kv-grid">
                <div class="kv"><div class="k">deployment_id</div><div class="v mono">#{{ selectedDeployment.id }}</div></div>
                <div class="kv"><div class="k">流程</div><div class="v">{{ flowLabelById(selectedDeployment.flow_code) }}</div></div>
                <div class="kv"><div class="k">ver_no</div><div class="v mono">v{{ selectedDeployment.ver_no }}</div></div>
                <div class="kv"><div class="k">mode</div><div class="v"><span class="tag mode">{{ selectedDeployment.mode }}</span></div></div>
                <div class="kv"><div class="k">status</div><div class="v"><span class="tag" :class="statusTag(selectedDeployment.status)">{{ selectedDeployment.status }}</span></div></div>
                <div class="kv"><div class="k">schedule_type</div><div class="v mono">{{ selectedDeployment.schedule_type }}</div></div>
                <div class="kv"><div class="k">env_profile</div><div class="v mono">{{ selectedDeployment.env_profile_code || "—" }}</div></div>
                <div class="kv">
                  <div class="k">worker_targeting</div>
                  <div class="v mono">
                    <template v-if="selectedDeployment.worker_targeting?.mode === 'pin'">
                      pin: {{ selectedDeployment.worker_targeting.worker_id }}
                    </template>
                    <template v-else-if="selectedDeployment.worker_targeting?.mode === 'pool'">
                      pool: {{ (selectedDeployment.worker_targeting.worker_ids || []).join(', ') || '—' }}
                    </template>
                    <template v-else>
                      any
                    </template>
                  </div>
                </div>
              </div>

              <div
                v-if="selectedDeployment.schedule_type === 'subscription'"
                class="side-section sub-obs-section"
                style="margin-top:12px;"
              >
                <div class="lbl">订阅消费可观测</div>
                <div v-if="loadingSubSummary" class="muted small pad">加载中…</div>
                <template v-else-if="subSummary">
                  <div v-if="subSummary.consumer_id" class="muted small" style="margin-bottom:8px;">
                    consumer <span class="mono">{{ subSummary.consumer_id }}</span>
                    <span v-if="subSummary.messages.last_updated_at">
                      · 最近消息 {{ formatTs(subSummary.messages.last_updated_at) }}
                    </span>
                  </div>
                  <div class="sub-obs-grid">
                    <article class="sub-obs-card">
                      <div class="sub-obs-card-title">消息账本</div>
                      <div class="ov-metrics">
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.messages.total }}</div>
                          <div class="ov-label">全部</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.messages.by_status.processing ?? 0 }}</div>
                          <div class="ov-label">processing</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.messages.by_status.completed ?? 0 }}</div>
                          <div class="ov-label">completed</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono" :class="{ bad: (subSummary.messages.by_status.failed ?? 0) > 0 }">
                            {{ subSummary.messages.by_status.failed ?? 0 }}
                          </div>
                          <div class="ov-label">failed</div>
                        </div>
                      </div>
                    </article>
                    <article class="sub-obs-card">
                      <div class="sub-obs-card-title">流程运行</div>
                      <div class="ov-metrics">
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.runs.total }}</div>
                          <div class="ov-label">全部</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.runs.by_status.running ?? 0 }}</div>
                          <div class="ov-label">running</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono">{{ subSummary.runs.by_status.completed ?? 0 }}</div>
                          <div class="ov-label">completed</div>
                        </div>
                        <div class="ov-metric">
                          <div class="ov-num mono" :class="{ bad: (subSummary.runs.by_status.failed ?? 0) > 0 }">
                            {{ subSummary.runs.by_status.failed ?? 0 }}
                          </div>
                          <div class="ov-label">failed</div>
                        </div>
                      </div>
                    </article>
                  </div>
                  <div v-if="subSummary.recent_failed_messages.length" class="sub-obs-failures">
                    <div class="lbl">最近失败消息</div>
                    <table class="grid-table mini">
                      <thead>
                        <tr>
                          <th>position</th>
                          <th style="width:90px">状态</th>
                          <th>error</th>
                          <th style="width:150px">时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="m in subSummary.recent_failed_messages"
                          :key="m.id"
                          class="clickable"
                          @click="openSubscriptionMessage(m)"
                        >
                          <td class="mono small">{{ m.topic }}:{{ m.partition }}:{{ m.offset }}</td>
                          <td><span class="tag small" :class="messageStatusTag(m.status)">{{ m.status }}</span></td>
                          <td class="small err-cell">{{ truncateText(m.error, 120) }}</td>
                          <td class="mono small">{{ formatTs(m.updated_at) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div class="ov-actions" style="margin-top:8px;">
                    <button type="button" class="btn small ghost" @click="depDetailTab = 'messages'; depMessagesOffset = 0; loadSubscriptionMessages()">
                      查看全部消息
                    </button>
                    <button type="button" class="btn small ghost" @click="loadSubscriptionSummary()">刷新</button>
                  </div>
                </template>
                <div v-else class="muted small pad">暂无消费统计</div>
              </div>

              <div v-if="selectedDeployment.status_detail" class="side-section" style="margin-top:12px;">
                <div class="lbl">异常诊断</div>
                <div class="diag">
                  <div class="diag-row">
                    <div class="diag-k">原因</div>
                    <div class="diag-v">
                      <span class="tag small" :class="statusTag(selectedDeployment.status)">
                        {{ statusDetailReasonLabel(selectedDeployment.status_detail) }}
                      </span>
                      <span v-if="statusDetailMessage(selectedDeployment.status_detail)" class="muted small" style="margin-left:8px;">
                        {{ statusDetailMessage(selectedDeployment.status_detail) }}
                      </span>
                    </div>
                  </div>
                  <div class="diag-row" v-if="statusDetailWhen(selectedDeployment.status_detail)">
                    <div class="diag-k">时间</div>
                    <div class="diag-v mono">{{ formatTs(statusDetailWhen(selectedDeployment.status_detail)) }}</div>
                  </div>
                  <div class="diag-row" v-if="statusDetailWorker(selectedDeployment.status_detail)">
                    <div class="diag-k">worker</div>
                    <div class="diag-v mono">{{ statusDetailWorker(selectedDeployment.status_detail) }}</div>
                  </div>
                  <div class="diag-row" v-if="statusDetailPool(selectedDeployment.status_detail)?.length">
                    <div class="diag-k">pool</div>
                    <div class="diag-v mono">{{ statusDetailPool(selectedDeployment.status_detail)!.join(", ") }}</div>
                  </div>
                  <div class="diag-row" v-if="statusDetailActiveCount(selectedDeployment.status_detail) != null">
                    <div class="diag-k">active_workers</div>
                    <div class="diag-v mono">{{ statusDetailActiveCount(selectedDeployment.status_detail) }}</div>
                  </div>
                  <div class="diag-row" v-if="statusDetailQueuedFailed(selectedDeployment.status_detail) != null">
                    <div class="diag-k">queued_failed</div>
                    <div class="diag-v mono">{{ statusDetailQueuedFailed(selectedDeployment.status_detail) }}</div>
                  </div>
                </div>

                <details class="diag-raw">
                  <summary class="muted small">原始 JSON</summary>
                  <pre class="cfg mono" style="margin-top:8px;">{{ JSON.stringify(selectedDeployment.status_detail, null, 2) }}</pre>
                </details>
              </div>

              <div class="side-section" style="margin-top:12px;">
                <div class="lbl">分配的 Worker</div>
                <ul v-if="selectedDeployment.assignments?.length" class="assn-list">
                  <li v-for="a in selectedDeployment.assignments" :key="a.id">
                    <span class="mono">{{ a.worker_id }}</span>
                    <span class="tag small">{{ a.role }}</span>
                    <span v-if="a.lease_expires_at" class="muted small">lease: {{ formatTs(a.lease_expires_at) }}</span>
                  </li>
                </ul>
                <div v-else class="muted small pad">尚未分配 worker</div>
              </div>
            </section>

            <section v-else-if="depDetailTab === 'config'" class="panel-body">
              <div class="lbl">部署配置（只读）</div>
              <pre class="cfg mono">{{ deploymentCfgText(selectedDeployment) }}</pre>
            </section>

            <section v-else-if="depDetailTab === 'messages'" class="panel-body">
              <div class="run-embed-toolbar">
                <span class="muted small">
                  消息账本 · 共 {{ subMessagesResp?.total ?? 0 }} 条 · 第 {{ Math.floor((subMessagesResp?.offset ?? 0) / depMessagesPageSize) + 1 }} 页
                </span>
                <span class="muted small">· 状态</span>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === '' }"
                  @click="depMessagesStatusFilter = ''; depMessagesOffset = 0; loadSubscriptionMessages()"
                >全部</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === 'processing' }"
                  @click="depMessagesStatusFilter = 'processing'; depMessagesOffset = 0; loadSubscriptionMessages()"
                >processing</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === 'completed' }"
                  @click="depMessagesStatusFilter = 'completed'; depMessagesOffset = 0; loadSubscriptionMessages()"
                >completed</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === 'failed' }"
                  @click="depMessagesStatusFilter = 'failed'; depMessagesOffset = 0; loadSubscriptionMessages()"
                >failed</button>
                <span class="spacer" />
                <button type="button" class="btn small ghost" :disabled="loadingSubMessages" @click="loadSubscriptionMessages()">刷新</button>
                <button type="button" class="btn small ghost" :disabled="(subMessagesResp?.offset ?? 0) === 0" @click="subMessagesPrevPage">上一页</button>
                <button type="button" class="btn small ghost" :disabled="!subMessagesHasNext" @click="subMessagesNextPage">下一页</button>
              </div>
              <table class="grid-table">
                <thead>
                  <tr>
                    <th style="width:200px">position</th>
                    <th style="width:100px">状态</th>
                    <th style="width:90px">run</th>
                    <th>error</th>
                    <th style="width:170px">updated_at</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="loadingSubMessages">
                    <td colspan="5" class="muted center">加载中…</td>
                  </tr>
                  <tr v-else-if="!subMessagesResp || subMessagesResp.messages.length === 0">
                    <td colspan="5" class="muted center">暂无消息记录</td>
                  </tr>
                  <tr v-for="m in subMessagesResp?.messages ?? []" :key="m.id">
                    <td class="mono small">{{ m.topic }}:{{ m.partition }}:{{ m.offset }}</td>
                    <td><span class="tag small" :class="messageStatusTag(m.status)">{{ m.status }}</span></td>
                    <td class="mono">
                      <button
                        v-if="m.deploy_run_id"
                        type="button"
                        class="linkish"
                        @click="openSubscriptionRun(m.deploy_run_id)"
                      >#{{ m.deploy_run_id }}</button>
                      <span v-else class="muted">—</span>
                    </td>
                    <td class="small err-cell">{{ truncateText(m.error, 200) }}</td>
                    <td class="mono small">{{ formatTs(m.updated_at) }}</td>
                  </tr>
                </tbody>
              </table>
            </section>

            <section v-else class="panel-body">
              <div
                v-if="selectedDeployment.schedule_type === 'subscription' && subSummary"
                class="sub-obs-banner"
              >
                <span class="muted small">订阅消费</span>
                <span class="mono small">消息 {{ subSummary.messages.total }}</span>
                <span class="mono small" :class="{ bad: (subSummary.messages.by_status.failed ?? 0) > 0 }">
                  失败 {{ subSummary.messages.by_status.failed ?? 0 }}
                </span>
                <span class="mono small">运行 {{ subSummary.runs.total }}</span>
                <button type="button" class="btn small ghost" @click="depDetailTab = 'messages'; depMessagesOffset = 0; loadSubscriptionMessages()">消息账本</button>
                <button type="button" class="btn small ghost" @click="loadSubscriptionSummary()">刷新统计</button>
              </div>
              <div class="run-embed-toolbar">
                <span class="muted small">
                  共 {{ depRunsResp?.total ?? 0 }} 条 · 第 {{ Math.floor((depRunsResp?.offset ?? 0) / depRunsPageSize) + 1 }} 页
                </span>
                <span class="muted small">· 状态</span>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === '' }"
                  @click="depRunsStatusFilter=''; depRunsOffset=0; loadEmbeddedDepRuns()"
                >全部</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'running' }"
                  @click="depRunsStatusFilter='running'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >running</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'failed' }"
                  @click="depRunsStatusFilter='failed'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >failed</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'completed' }"
                  @click="depRunsStatusFilter='completed'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >completed</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'terminated' }"
                  @click="depRunsStatusFilter='terminated'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >terminated</button>
                <span class="spacer" />
                <button type="button" class="btn small ghost" :disabled="loadingDepRuns" @click="loadEmbeddedDepRuns()">刷新</button>
                <button type="button" class="btn small ghost" :disabled="(depRunsResp?.offset ?? 0) === 0" @click="depRunsPrevPage">上一页</button>
                <button type="button" class="btn small ghost" :disabled="!depRunsHasNext" @click="depRunsNextPage">下一页</button>
              </div>

              <table class="grid-table">
                <thead>
                  <tr>
                    <th style="width:90px">run</th>
                    <th style="width:110px">状态</th>
                    <th style="width:80px">mode</th>
                    <th style="width:170px">started_at</th>
                    <th style="width:110px">耗时</th>
                    <th style="width:130px" title="累计 / 采样 Span 数">spans</th>
                    <th>worker</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="loadingDepRuns">
                    <td colspan="7" class="muted center">加载中…</td>
                  </tr>
                  <tr v-else-if="!depRunsResp || depRunsResp.runs.length === 0">
                    <td colspan="7" class="muted center">暂无运行记录</td>
                  </tr>
                  <tr
                    v-for="r in depRunsResp?.runs ?? []"
                    :key="r.id"
                    :class="{ active: selectedDepRunId === r.id }"
                    @click="selectEmbeddedDepRun(r.id)"
                  >
                    <td class="mono">
                      #{{ r.id }}
                      <button type="button" class="icon-btn" title="复制 run_id" @click.stop="copyText(String(r.id))">⧉</button>
                    </td>
                    <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
                    <td><span class="tag mode">{{ r.mode }}</span></td>
                    <td class="mono small">{{ formatTs(r.started_at) }}</td>
                    <td class="mono small">{{ runElapsed(r) }}</td>
                    <td class="mono small" :title="`总 ${r.span_count ?? 0} / 采样 ${r.sampled_span_count ?? 0}`">
                      {{ formatSpanCounters(r) }}
                    </td>
                    <td class="mono small">
                      {{ r.worker_id ?? "—" }}
                      <button
                        v-if="r.worker_id"
                        type="button"
                        class="icon-btn"
                        title="复制 worker_id"
                        @click.stop="copyText(String(r.worker_id))"
                      >⧉</button>
                    </td>
                  </tr>
                </tbody>
              </table>

              <RunDetailDrawer
                :open="selectedDepRunId != null"
                title="运行详情"
                :loading="loadingSelectedDepRun"
                :detail="selectedDepRunDetail"
                @close="
                  selectedDepRunId = null;
                  selectedDepRunDetail = null;
                  loadingSelectedDepRun = false;
                "
              />
            </section>
          </section>

          <!-- 空状态 -->
          <section v-else class="panel empty">
            <p class="muted center pad">从左侧选择一个部署开始操作，或点击“新建”创建部署</p>
          </section>
        </main>
      </div>
    </section>

    <!-- ===================== 运行历史 ===================== -->
    <section v-if="tab === 'runs'" class="tab-body">
      <div class="toolbar">
        <label class="ctl">
          <span>deployment_id</span>
          <input v-model="runFilters.deployment_id" type="number" class="inp mono" placeholder="（全部）" />
        </label>
        <label class="ctl">
          <span>流程</span>
          <select v-model="runFilters.flow_code" class="inp">
            <option value="">（全部）</option>
            <option v-for="f in flowOptions" :key="f.id" :value="f.id">
              {{ flowListItemLabel(f) }}
            </option>
          </select>
        </label>
        <label class="ctl">
          <span>worker</span>
          <input v-model="runFilters.worker_id" class="inp mono" placeholder="worker_id（全部）" />
        </label>
        <label class="ctl">
          <span>mode</span>
          <select v-model="runFilters.mode" class="inp">
            <option value="">全部</option>
            <option value="debug">debug</option>
            <option value="shadow">shadow</option>
            <option value="production">production</option>
          </select>
        </label>
        <label class="ctl">
          <span>状态</span>
          <select v-model="runFilters.status" class="inp">
            <option value="">全部</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="terminated">terminated</option>
          </select>
        </label>
        <button type="button" class="btn ghost" :disabled="loadingRuns" @click="loadRuns">查询</button>
        <span class="spacer" />
        <span class="muted small">共 {{ runsResp?.total ?? 0 }} 条 · 第 {{ Math.floor((runsResp?.offset ?? 0) / runPageSize) + 1 }} 页</span>
        <button type="button" class="btn small ghost" :disabled="(runsResp?.offset ?? 0) === 0" @click="prevPage">上一页</button>
        <button type="button" class="btn small ghost" :disabled="!hasNextPage" @click="nextPage">下一页</button>
      </div>

      <table class="grid-table">
        <thead>
          <tr>
            <th style="width:80px">run_id</th>
            <th>flow</th>
            <th style="width:90px">来源</th>
            <th style="width:80px">mode</th>
            <th style="width:110px">状态</th>
            <th style="width:160px">started_at</th>
            <th style="width:120px">耗时</th>
            <th style="width:130px" title="累计触发的 Span 数（采样前） / 实际写库数（采样后）">
              spans
            </th>
            <th>worker</th>
            <th style="width:100px">deployment</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loadingRuns"><td colspan="10" class="muted center">加载中…</td></tr>
          <tr v-else-if="!runsResp || runsResp.runs.length === 0">
            <td colspan="10" class="muted center">暂无运行记录</td>
          </tr>
          <tr
            v-for="r in runsResp?.runs ?? []"
            :key="r.id"
            :class="{ active: selectedRunId === r.id }"
            @click="selectRun(r.id)"
          >
            <td class="mono">#{{ r.id }}</td>
            <td>
              <div>{{ flowLabelById(r.flow_code) }}</div>
              <div class="muted small">v{{ r.ver_no }}</div>
            </td>
            <td>
              <span class="tag">{{ r.source || (r.test_batch_id ? "test_batch" : r.deployment_id ? "deployment" : "adhoc") }}</span>
            </td>
            <td><span class="tag mode">{{ r.mode }}</span></td>
            <td><span class="tag" :class="runStatusTag(r.status)">{{ r.status }}</span></td>
            <td class="mono small">{{ formatTs(r.started_at) }}</td>
            <td class="mono small">{{ runElapsed(r) }}</td>
            <td class="mono small" :title="`总 ${r.span_count ?? 0} / 采样 ${r.sampled_span_count ?? 0}`">
              {{ formatSpanCounters(r) }}
            </td>
            <td class="mono small">{{ r.worker_id ?? "—" }}</td>
            <td class="mono small">{{ r.deployment_id ? `#${r.deployment_id}` : "—" }}</td>
          </tr>
        </tbody>
      </table>

      <RunDetailDrawer
        :open="selectedRunId != null"
        title="运行详情"
        :loading="loadingRunDetail"
        :detail="selectedRunDetail"
        @close="
          selectedRunId = null;
          selectedRunDetail = null;
          loadingRunDetail = false;
        "
      />
    </section>

    <!-- ===================== 工作节点 ===================== -->
    <section v-if="tab === 'workers'" class="tab-body">
      <div class="toolbar">
        <span class="muted small">共 {{ workers.length }} 个 worker</span>
        <span class="spacer" />
        <button type="button" class="btn ghost" :disabled="loadingWorkers" @click="loadWorkers">刷新</button>
      </div>
      <div class="worker-grid">
        <article v-for="w in workers" :key="w.worker_id" class="worker-card" :class="workerStatusClass(w.status)">
          <header class="worker-head">
            <span class="worker-id mono">{{ w.worker_id }}</span>
            <span class="tag" :class="workerStatusClass(w.status)">{{ w.status }}</span>
          </header>
          <dl class="worker-meta">
            <div><dt>host</dt><dd class="mono">{{ w.host || "—" }}</dd></div>
            <div><dt>pid</dt><dd class="mono">{{ w.pid ?? "—" }}</dd></div>
            <div><dt>last_heartbeat</dt><dd class="mono small">{{ formatRelative(w.last_heartbeat) }}</dd></div>
            <div><dt>分配部署</dt><dd>{{ w.assigned_deployments.length }}</dd></div>
          </dl>
          <div v-if="w.assigned_deployments.length" class="worker-deps">
            <span v-for="id in w.assigned_deployments" :key="id" class="dep-chip">#{{ id }}</span>
          </div>
        </article>
        <p v-if="!loadingWorkers && workers.length === 0" class="muted center pad">暂无 worker（启动 ``flow-worker start`` 后自动注册）</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import {
  deleteDeployment,
  getDeployment,
  listDeployments,
  patchDeployment,
  type Deployment,
  type DeploymentDetail,
} from "@/api/deployments";
import { listWorkers, type Worker } from "@/api/workers";
import { getDeployRun, listDeployRuns } from "@/api/deployRuns";
import {
  getSubscriptionSummary,
  listSubscriptionMessages,
  type SubscriptionMessagesListResponse,
  type SubscriptionSummary,
} from "@/api/subscriptionObservability";
import type { FlowRunDetail, FlowRunSummary, FlowRunsListResponse } from "@/api/flowRuns";
import { useFlowLabels } from "@/composables/useFlowLabels";
import { fetchProfiles } from "@/api/profiles";
import RunDetailDrawer from "@/components/RunDetailDrawer.vue";
import DeploymentCreateForm from "@/components/DeploymentCreateForm.vue";

type TabId = "overview" | "deployments" | "runs" | "workers";

const TABS: { id: TabId; label: string }[] = [
  { id: "deployments", label: "部署管理" },
  { id: "runs", label: "运行实例" },
  { id: "workers", label: "工作节点" },
];

const tab = ref<TabId>("deployments");
const error = ref("");
const notice = ref("");

// ---------------- Confirm modal (unified) ----------------

const confirmOpen = ref(false);
const confirmBusy = ref(false);
const confirmTitle = ref("确认操作");
const confirmText = ref("");
const confirmCta = ref("确认");
let confirmFn: null | (() => Promise<void>) = null;

function openConfirm(opts: { title: string; text: string; cta?: string; fn: () => Promise<void> }) {
  confirmTitle.value = opts.title;
  confirmText.value = opts.text;
  confirmCta.value = opts.cta || "确认";
  confirmFn = opts.fn;
  confirmOpen.value = true;
  confirmBusy.value = false;
}

function closeConfirm() {
  if (confirmBusy.value) return;
  confirmOpen.value = false;
  confirmFn = null;
}

async function confirmExecute() {
  if (!confirmFn || confirmBusy.value) return;
  confirmBusy.value = true;
  try {
    await confirmFn();
    confirmOpen.value = false;
  } finally {
    confirmBusy.value = false;
    confirmFn = null;
  }
}

// ---------------- Deployments ----------------

const deployments = ref<Deployment[]>([]);
const loadingDep = ref(false);
const depFilters = reactive<{ flow_code: string; status: string; mode: string }>({
  flow_code: "",
  status: "",
  mode: "",
});
const selectedDeploymentId = ref<number | null>(null);
const selectedDeployment = ref<DeploymentDetail | null>(null);
const depDetailTab = ref<"overview" | "messages" | "runs" | "config">("overview");
const depWorkspace = ref<"overview" | "create" | "detail">("overview");

// Deployment list item "more" menu
const openDepMenuId = ref<number | null>(null);

function toggleDepMenu(id: number) {
  openDepMenuId.value = openDepMenuId.value === id ? null : id;
}

function closeDepMenu() {
  openDepMenuId.value = null;
}

function onDocPointerDown(e: PointerEvent) {
  if (openDepMenuId.value == null) return;
  const t = e.target as Node | null;
  const el = t instanceof Element ? t : null;
  if (!el || !el.closest(".dep2-menu-wrap")) {
    closeDepMenu();
  }
}

// Embedded runs inside deployment workbench
const depRunsPageSize = 20;
const depRunsOffset = ref(0);
const loadingDepRuns = ref(false);
const depRunsResp = ref<FlowRunsListResponse | null>(null);
const selectedDepRunId = ref<number | null>(null);
const selectedDepRunDetail = ref<FlowRunDetail | null>(null);
const loadingSelectedDepRun = ref(false);
const depRunsStatusFilter = ref("");

const subSummary = ref<SubscriptionSummary | null>(null);
const loadingSubSummary = ref(false);
const depMessagesPageSize = 25;
const depMessagesOffset = ref(0);
const depMessagesStatusFilter = ref("");
const loadingSubMessages = ref(false);
const subMessagesResp = ref<SubscriptionMessagesListResponse | null>(null);

const subMessagesHasNext = computed(() => {
  if (!subMessagesResp.value) return false;
  return (
    subMessagesResp.value.offset + subMessagesResp.value.messages.length
    < subMessagesResp.value.total
  );
});

const depRunsHasNext = computed(() => {
  if (!depRunsResp.value) return false;
  return depRunsResp.value.offset + depRunsResp.value.runs.length < depRunsResp.value.total;
});

const depCount = computed(() => {
  const out = { pending: 0, running: 0, stopping: 0, stopped: 0, failed: 0 };
  for (const d of deployments.value) {
    const st = String(d.status || "");
    if (st in out) (out as any)[st] += 1;
  }
  return out;
});

const creatingDeployment = ref(false);
const formError = ref("");
const deployCreateFormRef = ref<InstanceType<typeof DeploymentCreateForm> | null>(null);
const { flowOptions, ensureFlowList, flowLabelById } = useFlowLabels();

const filteredDeployments = computed(() => {
  const q = depFilters.flow_code.trim().toLowerCase();
  if (!q) return deployments.value;
  return deployments.value.filter((d) => {
    const label = flowLabelById(d.flow_code).toLowerCase();
    return label.includes(q) || d.flow_code.toLowerCase().includes(q);
  });
});
const profileOptions = ref<string[]>([]);

async function loadDeployments() {
  loadingDep.value = true;
  error.value = "";
  try {
    await ensureFlowList();
    const res = await listDeployments({
      status: depFilters.status || undefined,
      mode: depFilters.mode || undefined,
      root_only: true,
    });
    deployments.value = res.deployments;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingDep.value = false;
  }
}

async function selectDeployment(id: number) {
  creatingDeployment.value = false;
  selectedDeploymentId.value = id;
  depDetailTab.value = "overview";
  depWorkspace.value = "detail";
  // reset embedded runs state
  depRunsOffset.value = 0;
  depRunsResp.value = null;
  selectedDepRunId.value = null;
  selectedDepRunDetail.value = null;
  subSummary.value = null;
  subMessagesResp.value = null;
  depMessagesOffset.value = 0;
  try {
    selectedDeployment.value = await getDeployment(id);
    if (selectedDeployment.value?.schedule_type === "subscription") {
      await loadSubscriptionSummary();
      if (depDetailTab.value === "messages") {
        await loadSubscriptionMessages();
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function patchStatus(id: number, status: "stopping" | "pending") {
  try {
    await patchDeployment(id, status);
    await loadDeployments();
    if (selectedDeploymentId.value === id) {
      await selectDeployment(id);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function requestStopDeployment(id: number) {
  const d = deployments.value.find((x) => x.id === id);
  const label = d ? `${flowLabelById(d.flow_code)} v${d.ver_no}` : "";
  openConfirm({
    title: "确认停止部署",
    text: `确认停止部署 #${id}${label ? `（${label}）` : ""} 吗？Worker 将尝试停止该部署的运行。`,
    cta: "确认停止",
    fn: async () => patchStatus(id, "stopping"),
  });
}

function requestStartDeployment(id: number) {
  const d = deployments.value.find((x) => x.id === id);
  const label = d ? `${flowLabelById(d.flow_code)} v${d.ver_no}` : "";
  openConfirm({
    title: "确认启动部署",
    text: `确认启动部署 #${id}${label ? `（${label}）` : ""} 吗？系统将入队并分配 worker。`,
    cta: "确认启动",
    fn: async () => patchStatus(id, "pending"),
  });
}

function requestRestartDeployment(id: number) {
  // restart is less risky than stop, but still makes side effects; keep it explicit.
  const d = deployments.value.find((x) => x.id === id);
  const label = d ? `${flowLabelById(d.flow_code)} v${d.ver_no}` : "";
  openConfirm({
    title: "确认重启部署",
    text: `确认重启部署 #${id}${label ? `（${label}）` : ""} 吗？系统将重新入队并分配 worker。`,
    cta: "确认重启",
    fn: async () => patchStatus(id, "pending"),
  });
}

async function removeDeployment(id: number) {
  const d = deployments.value.find((x) => x.id === id);
  const label = d ? `${flowLabelById(d.flow_code)} v${d.ver_no}` : "";
  openConfirm({
    title: "确认删除部署",
    text: `确认删除部署 #${id}${label ? `（${label}）` : ""} 吗？该操作为软删除。`,
    cta: "确认删除",
    fn: async () => {
      await deleteDeployment(id);
      if (selectedDeploymentId.value === id) {
        selectedDeploymentId.value = null;
        selectedDeployment.value = null;
      }
      await loadDeployments();
    },
  });
}

function viewRuns(d: Deployment, opts?: { forceGlobal?: boolean }) {
  runFilters.deployment_id = d.id;
  runFilters.flow_code = "";
  runFilters.worker_id = "";
  runFilters.mode = "";
  runFilters.status = "";
  // If user is already in deployments workbench, show embedded runs (no page jump),
  // unless explicitly forcing global navigation.
  if (tab.value === "deployments" && !opts?.forceGlobal) {
    depDetailTab.value = "runs";
    depRunsOffset.value = 0;
    void loadEmbeddedDepRuns();
    return;
  }
  // Otherwise, go to global runs page.
  depDetailTab.value = "runs";
  switchTab("runs");
}

async function loadEmbeddedDepRuns() {
  if (!selectedDeploymentId.value) return;
  loadingDepRuns.value = true;
  error.value = "";
  try {
    if (selectedDeployment.value?.schedule_type === "subscription") {
      await loadSubscriptionSummary();
    }
    depRunsResp.value = await listDeployRuns({
      deployment_id: selectedDeploymentId.value,
      status: depRunsStatusFilter.value || undefined,
      offset: depRunsOffset.value,
      limit: depRunsPageSize,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingDepRuns.value = false;
  }
}

async function loadSubscriptionSummary() {
  if (!selectedDeploymentId.value) return;
  if (selectedDeployment.value?.schedule_type !== "subscription") return;
  loadingSubSummary.value = true;
  try {
    subSummary.value = await getSubscriptionSummary(selectedDeploymentId.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingSubSummary.value = false;
  }
}

async function loadSubscriptionMessages() {
  if (!selectedDeploymentId.value) return;
  loadingSubMessages.value = true;
  error.value = "";
  try {
    subMessagesResp.value = await listSubscriptionMessages(selectedDeploymentId.value, {
      status: depMessagesStatusFilter.value || undefined,
      offset: depMessagesOffset.value,
      limit: depMessagesPageSize,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingSubMessages.value = false;
  }
}

function subMessagesPrevPage() {
  depMessagesOffset.value = Math.max(0, depMessagesOffset.value - depMessagesPageSize);
  void loadSubscriptionMessages();
}

function subMessagesNextPage() {
  if (!subMessagesHasNext.value) return;
  depMessagesOffset.value += depMessagesPageSize;
  void loadSubscriptionMessages();
}

function openSubscriptionMessage(m: { status: string; deploy_run_id: number | null }) {
  depMessagesStatusFilter.value = m.status;
  depMessagesOffset.value = 0;
  depDetailTab.value = "messages";
  void loadSubscriptionMessages();
  if (m.deploy_run_id) {
    void openSubscriptionRun(m.deploy_run_id);
  }
}

async function openSubscriptionRun(runId: number) {
  depDetailTab.value = "runs";
  depRunsOffset.value = 0;
  await loadEmbeddedDepRuns();
  await selectEmbeddedDepRun(runId);
}

async function copyText(text: string) {
  const v = String(text ?? "").trim();
  if (!v) return;
  try {
    await navigator.clipboard.writeText(v);
    notice.value = `已复制：${v}`;
    window.setTimeout(() => {
      if (notice.value === `已复制：${v}`) notice.value = "";
    }, 1200);
  } catch {
    // best effort fallback
    try {
      const ta = document.createElement("textarea");
      ta.value = v;
      ta.style.position = "fixed";
      ta.style.left = "-10000px";
      ta.style.top = "-10000px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      notice.value = `已复制：${v}`;
      window.setTimeout(() => {
        if (notice.value === `已复制：${v}`) notice.value = "";
      }, 1200);
    } catch {
      notice.value = "复制失败（浏览器权限限制）";
      window.setTimeout(() => (notice.value = ""), 1400);
    }
  }
}

async function selectEmbeddedDepRun(id: number) {
  selectedDepRunId.value = id;
  loadingSelectedDepRun.value = true;
  error.value = "";
  try {
    selectedDepRunDetail.value = await getDeployRun(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingSelectedDepRun.value = false;
  }
}

function depRunsPrevPage() {
  depRunsOffset.value = Math.max(0, depRunsOffset.value - depRunsPageSize);
  void loadEmbeddedDepRuns();
}

function depRunsNextPage() {
  if (!depRunsHasNext.value) return;
  depRunsOffset.value += depRunsPageSize;
  void loadEmbeddedDepRuns();
}

async function openCreateForm() {
  creatingDeployment.value = true;
  depWorkspace.value = "create";
  selectedDeploymentId.value = null;
  selectedDeployment.value = null;
  depDetailTab.value = "overview";
  formError.value = "";
  deployCreateFormRef.value?.reset();
  try {
    await ensureFlowList();
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
  if (profileOptions.value.length === 0) {
    try {
      const res = await fetchProfiles();
      profileOptions.value = res.profiles;
    } catch {
      // best effort
    }
  }
  if (workers.value.length === 0) {
    try {
      await loadWorkers();
    } catch {
      // ignore; create form still usable without workers list
    }
  }
}

function openDeployOverview() {
  creatingDeployment.value = false;
  depWorkspace.value = "overview";
  selectedDeploymentId.value = null;
  selectedDeployment.value = null;
  depDetailTab.value = "overview";
  closeDepMenu();
  // ensure overview data is available
  if (deployments.value.length === 0) loadDeployments();
  if (workers.value.length === 0) loadWorkers();
  loadRuns();
}

async function onDeploymentCreated(id: number) {
  creatingDeployment.value = false;
  formError.value = "";
  await loadDeployments();
  selectDeployment(id);
}

function deploymentCfgText(d: DeploymentDetail): string {
  return JSON.stringify(
    {
      schedule_config: d.schedule_config,
      worker_policy: d.worker_policy,
      capability_policy: d.capability_policy,
      worker_targeting: d.worker_targeting,
      env_profile_code: d.env_profile_code,
    },
    null,
    2,
  );
}

// ---------------- Flow runs ----------------

const runFilters = reactive<{
  deployment_id: number | null;
  source: string;
  flow_code: string;
  mode: string;
  status: string;
  worker_id: string;
}>({
  deployment_id: null,
  // 运行中心只展示部署运行实例，测试运行已在数据层隔离。
  source: "deployment",
  flow_code: "",
  mode: "",
  status: "",
  worker_id: "",
});
const runPageSize = 50;
const runOffset = ref(0);
const loadingRuns = ref(false);
const runsResp = ref<FlowRunsListResponse | null>(null);
const selectedRunId = ref<number | null>(null);
const selectedRunDetail = ref<FlowRunDetail | null>(null);
const loadingRunDetail = ref(false);

const hasNextPage = computed(() => {
  if (!runsResp.value) return false;
  return runsResp.value.offset + runsResp.value.runs.length < runsResp.value.total;
});

async function loadRuns() {
  loadingRuns.value = true;
  error.value = "";
  try {
    await ensureFlowList();
    runsResp.value = await listDeployRuns({
      deployment_id: runFilters.deployment_id != null && Number(runFilters.deployment_id) > 0
        ? Number(runFilters.deployment_id)
        : undefined,
      flow_code: runFilters.flow_code.trim() || undefined,
      mode: runFilters.mode || undefined,
      status: runFilters.status || undefined,
      worker_id: runFilters.worker_id.trim() || undefined,
      offset: runOffset.value,
      limit: runPageSize,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRuns.value = false;
  }
}

function prevPage() {
  runOffset.value = Math.max(0, runOffset.value - runPageSize);
  loadRuns();
}

function nextPage() {
  if (!hasNextPage.value) return;
  runOffset.value += runPageSize;
  loadRuns();
}

async function selectRun(id: number) {
  selectedRunId.value = id;
  loadingRunDetail.value = true;
  try {
    selectedRunDetail.value = await getDeployRun(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingRunDetail.value = false;
  }
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
  if (diff < 3600_000) return `${(diff / 60_000).toFixed(1)}min`;
  return `${(diff / 3600_000).toFixed(1)}h`;
}

/** Compact spans column: ``总 / 采样`` with short formatting. */
function formatSpanCounters(r: FlowRunSummary): string {
  const total = r.span_count;
  const sampled = r.sampled_span_count;
  if (total == null && sampled == null) return "—";
  return `${shortNum(total)} / ${shortNum(sampled)}`;
}

function shortNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

watch(
  () => runFilters.deployment_id,
  () => {
    runOffset.value = 0;
  },
);

// ---------------- Workers ----------------

const workers = ref<Worker[]>([]);
const loadingWorkers = ref(false);

const activeWorkers = computed(() => {
  return workers.value.filter((w) => String(w.status || "") === "active");
});

watch(
  () => workers.value.map((w) => `${w.worker_id}:${w.status}`),
  () => {
    // Keep selection consistent: only allow selecting active workers.
    const active = new Set(activeWorkers.value.map((w) => w.worker_id));
    for (const wid of [...workerSelected]) {
      if (!active.has(wid)) workerSelected.delete(wid);
    }
  },
);

const workerCount = computed(() => {
  const out = { active: 0, idle: 0, dead: 0, other: 0 };
  for (const w of workers.value) {
    const st = String(w.status || "");
    if (st === "active") out.active += 1;
    else if (st === "idle") out.idle += 1;
    else if (st === "dead") out.dead += 1;
    else out.other += 1;
  }
  return out;
});

async function loadWorkers() {
  loadingWorkers.value = true;
  error.value = "";
  try {
    const res = await listWorkers();
    workers.value = res.workers;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingWorkers.value = false;
  }
}

// ---------------- Helpers ----------------

function switchTab(id: TabId) {
  tab.value = id;
  if (id === "deployments" && deployments.value.length === 0) loadDeployments();
  if (id === "runs") loadRuns();
  if (id === "workers" && workers.value.length === 0) loadWorkers();
}

function reloadActive() {
  if (tab.value === "deployments") {
    loadDeployments();
    loadWorkers();
    loadRuns();
  } else if (tab.value === "runs") loadRuns();
  else loadWorkers();
}

function statusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed" || status === "stopped") return "ok";
  if (status === "failed") return "bad";
  if (status === "stopping") return "warn";
  return "info";
}

function runStatusTag(status: string): string {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  if (status === "terminated") return "warn";
  return "info";
}

function messageStatusTag(status: string): string {
  if (status === "processing") return "running";
  if (status === "completed") return "ok";
  if (status === "failed") return "bad";
  return "info";
}

function truncateText(text: string | null | undefined, maxLen: number): string {
  const t = String(text ?? "").trim();
  if (!t) return "—";
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen)}…`;
}

function workerStatusClass(status: string): string {
  if (status === "active") return "ok";
  if (status === "dead") return "dead";
  if (status === "idle") return "warn";
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

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  if (diff < 0) return formatTs(iso);
  if (diff < 60_000) return `${Math.round(diff / 1000)}s 前`;
  if (diff < 3600_000) return `${Math.round(diff / 60_000)}min 前`;
  if (diff < 86400_000) return `${Math.round(diff / 3600_000)}h 前`;
  return formatTs(iso);
}

function statusDetailReasonLabel(detail: any): string {
  const reason = String(detail?.reason || "").trim();
  if (reason === "no_eligible_worker") return "无可用工作节点";
  if (reason === "pin_worker_offline") return "绑定节点离线";
  if (reason === "subscription_ingress_failed") return "订阅接入失败";
  return reason || "异常";
}

function statusDetailMessage(detail: any): string {
  const msg = detail?.message;
  return typeof msg === "string" ? msg : "";
}

function statusDetailWhen(detail: any): string | null {
  const ts = detail?.ts;
  return typeof ts === "string" ? ts : null;
}

function statusDetailWorker(detail: any): string | null {
  const w = detail?.worker_id;
  return typeof w === "string" && w ? w : null;
}

function statusDetailQueuedFailed(detail: any): number | null {
  const n = detail?.queued_failed;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function statusDetailActiveCount(detail: any): number | null {
  const n = detail?.active_worker_count;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function statusDetailPool(detail: any): string[] | null {
  const t = detail?.targeting;
  if (t && typeof t === "object" && t.mode === "pool" && Array.isArray(t.worker_ids)) {
    return t.worker_ids.map((x: any) => String(x)).filter((x: string) => x);
  }
  return null;
}

void switchTab("deployments");
// Ensure the deployments workbench opens on overview by default.
if (tab.value === "deployments") openDeployOverview();

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown, true);
  void ensureFlowList();
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", onDocPointerDown, true);
});
</script>

<style scoped>
.ops-page {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: auto;
}

.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 16px;
  font-weight: 700;
}

.subtitle {
  font-size: 12px;
  color: var(--muted);
}

.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
}

.tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 6px 14px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
}

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 700;
}

.tab-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.tab-body--fill {
  flex: 1;
  overflow: hidden;
}

.diag {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--surface-2);
}

.diag-row {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border);
}

.diag-row:last-child {
  border-bottom: none;
}

.diag-k {
  width: 120px;
  color: var(--muted);
  font-size: 12px;
}

.diag-v {
  flex: 1;
  min-width: 0;
}

.diag-raw {
  margin-top: 10px;
}

.diag-raw summary {
  cursor: pointer;
}

.confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 50;
}

.confirm-dialog {
  width: min(520px, 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm-title {
  font-weight: 800;
  font-size: 14px;
}

.confirm-text {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.sub-obs-section .sub-obs-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.sub-obs-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fbfdff;
}

.sub-obs-card-title {
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--muted);
}

.sub-obs-failures {
  margin-top: 12px;
}

.sub-obs-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  margin-bottom: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent-soft) 35%, transparent);
}

.err-cell {
  color: color-mix(in srgb, var(--danger, #c0392b) 85%, var(--text));
  word-break: break-word;
}

tr.clickable {
  cursor: pointer;
}

tr.clickable:hover td {
  background: color-mix(in srgb, var(--accent-soft) 45%, transparent);
}

.linkish {
  border: none;
  background: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
  font: inherit;
}

@media (max-width: 900px) {
  .sub-obs-section .sub-obs-grid {
    grid-template-columns: 1fr;
  }
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

.ov-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.ov-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ov-title {
  font-weight: 700;
  font-size: 13px;
}

.ov-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.ov-metric {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fbfdff;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ov-num {
  font-size: 18px;
  font-weight: 800;
  line-height: 1.05;
}

.ov-label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ov-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.bad {
  color: #b91c1c;
}

.grid-table.mini th,
.grid-table.mini td {
  padding: 6px 10px;
}

.ov-table-wrap {
  overflow: auto;
  min-width: 0;
  border-radius: 10px;
}

@media (max-width: 980px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.toolbar.sticky {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 92%, white);
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.06);
}

.toolbar-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-right: 6px;
}

.toolbar-h {
  font-weight: 800;
  font-size: 12px;
  color: var(--text);
}

.spacer {
  flex: 1;
}

.ctl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--muted);
}

.inp {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 9px;
  background: #fff;
  font-size: 12px;
  min-width: 140px;
}

.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
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

.btn.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
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

.err {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #fecaca 30%, transparent);
  color: #b91c1c;
  font-size: 12px;
}

.notice {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, #bbf7d0 22%, transparent);
  color: #047857;
  font-size: 12px;
  border: 1px solid color-mix(in srgb, #10b981 30%, transparent);
}

.grid-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

/* Panel: unified card container (used in workbench) */
.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.panel.empty {
  align-items: center;
  justify-content: center;
  min-height: 220px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-title {
  font-weight: 800;
  font-size: 14px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.dep-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 12px;
  min-height: 0;
  align-items: start;
}

.dep-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.dep-side {
  min-width: 0;
  min-height: 0;
}

.sticky-panel {
  position: sticky;
  top: 0;
  max-height: calc(100vh - 120px);
  overflow: auto;
}

.quick-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.chip {
  border: 1px solid var(--border);
  background: #fbfdff;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
}

.chip:hover {
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
}

.chip.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--accent);
  font-weight: 700;
}

.empty-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.muted {
  color: var(--muted);
}

.center {
  text-align: center;
}

.small {
  font-size: 11px;
}

.row-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.tag.small {
  font-size: 9px;
}

.tag.mode {
  background: color-mix(in srgb, #6366f1 12%, transparent);
  color: #4338ca;
  border-color: color-mix(in srgb, #6366f1 30%, transparent);
}

.tag.ok {
  background: color-mix(in srgb, #10b981 14%, transparent);
  color: #047857;
  border-color: color-mix(in srgb, #10b981 35%, transparent);
}

.tag.bad {
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, transparent);
}

.tag.dead {
  background: color-mix(in srgb, #94a3b8 18%, transparent);
  color: #475569;
  border-color: color-mix(in srgb, #94a3b8 40%, transparent);
}

.tag.warn {
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: #92400e;
  border-color: color-mix(in srgb, #f59e0b 35%, transparent);
}

.tag.running {
  background: color-mix(in srgb, #3b82f6 14%, transparent);
  color: #1d4ed8;
  border-color: color-mix(in srgb, #3b82f6 35%, transparent);
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lbl {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}

.assn-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.assn-list li {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfdff;
  font-size: 11px;
  flex-wrap: wrap;
}

.cfg {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: #0b1220;
  color: #e2e8f0;
  font-size: 11px;
  line-height: 1.4;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.rr-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.worker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.worker-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.worker-card.ok { border-left: 4px solid #10b981; }
.worker-card.dead { border-left: 4px solid #94a3b8; }
.worker-card.warn { border-left: 4px solid #f59e0b; }
.worker-card.info { border-left: 4px solid #94a3b8; }

.worker-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.worker-id {
  font-weight: 700;
  font-size: 12px;
}

.worker-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 10px;
  margin: 0;
  font-size: 11px;
}

.worker-meta dt {
  color: var(--muted);
  font-weight: 500;
  margin: 0;
}

.worker-meta dd {
  margin: 0;
  font-weight: 600;
}

.worker-deps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.dep-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.pad {
  padding: 12px;
}

.mono {
  font-family: var(--mono);
}
.mode-switch{
  display:flex;
  align-items:center;
  gap:8px;
  flex-wrap:wrap;
}
.mode-hint{
  flex:1;
  min-width:240px;
}
.targeting-grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap:10px;
}
.targeting-grid .ctl{
  display:flex;
  flex-direction:column;
  gap:6px;
}
@media (max-width: 860px){
  .targeting-grid{ grid-template-columns: 1fr; }
}

@media (max-width: 1080px) {
  .dep-layout {
    grid-template-columns: 1fr;
  }
  .sticky-panel {
    position: static;
    max-height: none;
  }
}

/* ---------------- Deployments v2 (sidebar + workbench) ---------------- */

.dep2-layout {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 12px;
  min-height: 0;
  flex: 1;
  align-items: stretch;
}

.dep2-sidebar {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
  min-height: 0;
}

.dep2-sidehead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.dep2-nav {
  display: flex;
  gap: 6px;
  align-items: center;
}

.dep2-title {
  font-size: 13px;
  font-weight: 800;
}

.dep2-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dep2-filter-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.dep2-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.dep2-filterbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dep2-search {
  flex: 1;
  min-width: 0;
}

.dep2-filterbar .inp {
  padding: 6px 10px;
}

.dep2-filter-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dep2-filter-row {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: nowrap;
}

.dep2-filter-label {
  min-width: 28px;
  flex: 0 0 auto;
}

.dep2-filter-scroll {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  padding-bottom: 0;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none; /* Firefox */
  position: relative;
}

/* Ensure filter button rows never wrap (override .seg-tabs default wrap). */
.dep2-filter-scroll.seg-tabs {
  flex-wrap: nowrap;
}

.dep2-filter-scroll::-webkit-scrollbar {
  height: 0px; /* hide but keep scroll */
}

.dep2-filter-scroll::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: 999px;
}

.dep2-filter-scroll::after {
  content: "";
  position: sticky;
  right: 0;
  top: 0;
  height: 100%;
  width: 18px;
  margin-left: auto;
  pointer-events: none;
  background: linear-gradient(to left, var(--surface) 20%, rgba(255, 255, 255, 0));
}

.dep2-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dep2-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  background: #fbfdff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dep2-item:hover {
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
}

.dep2-item.active {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.dep2-row1,
.dep2-row3 {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dep2-id {
  font-weight: 800;
  font-size: 12px;
}

.dep2-flow {
  font-weight: 700;
  font-size: 12px;
}

.dep2-row2 {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dep2-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dep2-main > .workbench-panel {
  flex: 1;
  min-height: 0;
}

.dep2-main > .panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.seg.jump {
  color: var(--muted);
  background: #fbfdff;
}

.seg.jump:hover {
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
  color: var(--text);
}

.jump-ico {
  font-weight: 900;
  margin-left: 2px;
  font-size: 12px;
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
  z-index: 30;
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

.dep2-menu-wrap {
  position: relative;
}

.seg-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.seg {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  white-space: nowrap;
}

.seg.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  font-weight: 700;
}

.seg-tabs.compact {
  border-bottom: none;
  padding-bottom: 0;
  gap: 6px;
}

.seg-tabs.compact .seg {
  padding: 4px 8px;
  font-size: 9px;
}

.seg-tabs.compact .seg.active {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.panel-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.run-embed-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.icon-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  border-radius: 6px;
  padding: 2px 6px;
  margin-left: 6px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}

.icon-btn:hover {
  background: color-mix(in srgb, var(--accent-soft) 55%, transparent);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
  color: var(--text);
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.kv {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fbfdff;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.kv .k {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}

.kv .v {
  font-size: 12px;
  color: var(--text);
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1080px) {
  .dep2-layout {
    grid-template-columns: 1fr;
  }
  .dep2-sidebar {
    max-height: none;
  }
  .kv-grid {
    grid-template-columns: 1fr;
  }
}
</style>
