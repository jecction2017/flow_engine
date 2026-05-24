<template>
  <div class="ops-page">
    <header class="top">
      <div class="top-head">
        <button
          type="button"
          class="dep-overview-back"
          :class="{ active: tab === 'deployments' && depWorkspace === 'overview' }"
          :title="DEP_CENTER_OVERVIEW_LABEL"
          :aria-label="`返回${DEP_CENTER_OVERVIEW_LABEL}`"
          :aria-current="tab === 'deployments' && depWorkspace === 'overview' ? 'page' : undefined"
          @click="openDeployOverview()"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.75" />
            <rect x="13" y="3" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.75" />
            <rect x="3" y="13" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.75" />
            <rect x="13" y="13" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.75" />
          </svg>
        </button>
        <div>
          <div class="title">运行中心</div>
          <div class="subtitle">部署管理 · 运行记录 · 工作节点状态</div>
        </div>
      </div>
      <button type="button" class="btn primary" @click="openCreateForm()">+ 新建部署</button>
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
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'running' }" :title="`${deploymentStatusLabel('running')} ${depCount.running}`" @click="depFilters.status='running'; loadDeployments()">{{ deploymentStatusLabel('running') }}</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'pending' }" :title="`${deploymentStatusLabel('pending')} ${depCount.pending}`" @click="depFilters.status='pending'; loadDeployments()">{{ deploymentStatusLabel('pending') }}</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'stopping' }" :title="`${deploymentStatusLabel('stopping')} ${depCount.stopping}`" @click="depFilters.status='stopping'; loadDeployments()">{{ deploymentStatusLabel('stopping') }}</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'stopped' }" :title="`${deploymentStatusLabel('stopped')} ${depCount.stopped}`" @click="depFilters.status='stopped'; loadDeployments()">{{ deploymentStatusLabel('stopped') }}</button>
                  <button type="button" class="seg" :class="{ active: depFilters.status === 'failed' }" :title="`${deploymentStatusLabel('failed')} ${depCount.failed}`" @click="depFilters.status='failed'; loadDeployments()">{{ deploymentStatusLabel('failed') }}</button>
                </div>
              </div>

              <div class="dep2-filter-row">
                <span class="muted small dep2-filter-label">部署方式</span>
                <div class="seg-tabs compact dep2-filter-scroll" style="border:none; padding:0;">
                  <button type="button" class="seg" :class="{ active: depFilters.mode === '' }" @click="depFilters.mode=''; loadDeployments()">全部</button>
                  <button type="button" class="seg" :class="{ active: depFilters.mode === 'production' }" @click="depFilters.mode='production'; loadDeployments()">{{ deploymentModeLabel('production') }}</button>
                  <button type="button" class="seg" :class="{ active: depFilters.mode === 'shadow' }" @click="depFilters.mode='shadow'; loadDeployments()">{{ deploymentModeLabel('shadow') }}</button>
                </div>
              </div>
            </div>
          </div>

          <ul class="dep2-list" role="listbox" aria-label="deployments">
            <li v-if="loadingDep" class="muted small pad center">加载中…</li>
            <li v-else-if="filteredDeployments.length === 0" class="muted small pad center">
              {{ deployments.length === 0 ? "暂无部署，建议先创建一个生产或灰度部署" : "无匹配的部署" }}
            </li>
            <li
              v-for="d in filteredDeployments"
              :key="d.id"
              class="dep2-item"
              :class="[deploymentListItemMod(d.mode), { active: selectedDeploymentId === d.id }]"
              role="option"
              :aria-selected="selectedDeploymentId === d.id"
              :title="deploymentListItemTitle(d)"
              @click="selectDeployment(d.id)"
            >
              <div class="dep2-line dep2-line--main">
                <span class="dep2-flow-group">
                  <span class="dep2-flow">{{ flowLabelById(d.flow_code) }}</span>
                  <span class="dep2-ver mono">v{{ d.ver_no }}</span>
                </span>
                <span class="tag dep-status-tag" :class="statusTag(d.status)">{{ deploymentStatusLabel(d.status) }}</span>
              </div>
              <div class="dep2-line dep2-line--meta">
                <div class="dep2-meta-cluster">
                  <span class="mono dep2-id-sm">#{{ d.id }}</span>
                  <span class="dep-mode dep-mode--compact" :class="deploymentModeMod(d.mode)">
                    {{ deploymentModeLabel(d.mode) }}
                  </span>
                  <span class="dep2-meta-rest muted small">{{ deploymentListMetaRest(d) }}</span>
                </div>
                <span class="dep2-time muted small mono">{{ formatRelative(d.updated_at || d.created_at) }}</span>
              </div>
            </li>
          </ul>
        </aside>

        <!-- 右侧：部署工作台 -->
        <main class="dep2-main">
          <section v-if="depWorkspace === 'overview'" class="panel">
            <header class="panel-head">
              <div>
                <div class="panel-title">总概览</div>
              </div>
            </header>

            <div class="center-overview-layout">
              <div class="center-overview-stats">
                <article class="ov-card">
                  <div class="ov-head">
                    <div class="ov-title">部署</div>
                    <button type="button" class="btn small ghost" @click="openCreateForm">+ 新建部署</button>
                  </div>
                  <div class="ov-metrics">
                    <div class="ov-metric"><div class="ov-num mono">{{ deployments.length }}</div><div class="ov-label">全部</div></div>
                    <div class="ov-metric"><div class="ov-num mono">{{ depCount.running }}</div><div class="ov-label">{{ deploymentStatusLabel('running') }}</div></div>
                    <div class="ov-metric"><div class="ov-num mono">{{ depCount.pending }}</div><div class="ov-label">{{ deploymentStatusLabel('pending') }}</div></div>
                    <div class="ov-metric"><div class="ov-num mono" :class="{ bad: depCount.failed > 0 }">{{ depCount.failed }}</div><div class="ov-label">{{ deploymentStatusLabel('failed') }}</div></div>
                  </div>
                </article>

                <article class="ov-card">
                  <div class="ov-head">
                    <div class="ov-title">工作节点</div>
                    <button type="button" class="btn small ghost" @click="switchTab('workers')">查看节点</button>
                  </div>
                  <div class="ov-metrics">
                    <div class="ov-metric"><div class="ov-num mono">{{ workers.length }}</div><div class="ov-label">全部</div></div>
                    <div class="ov-metric"><div class="ov-num mono">{{ workerCount.active }}</div><div class="ov-label">{{ workerStatusLabel('active') }}</div></div>
                    <div class="ov-metric"><div class="ov-num mono">{{ workerCount.idle }}</div><div class="ov-label">{{ workerStatusLabel('idle') }}</div></div>
                    <div class="ov-metric"><div class="ov-num mono">{{ workerCount.dead }}</div><div class="ov-label">{{ workerStatusLabel('dead') }}</div></div>
                  </div>
                </article>
              </div>

              <div class="center-overview-runs-row">
                <article class="ov-card">
                  <div class="ov-head">
                    <div class="ov-head-main">
                      <div class="ov-title">最近运行</div>
                      <span class="muted small">近 {{ CENTER_OVERVIEW_LOOKBACK_HOURS }} 小时 · 不含失败 · 每部署最新一条</span>
                    </div>
                    <button type="button" class="btn small ghost" @click="openRunsTab()">打开运行记录</button>
                  </div>
                  <div
                    class="ov-table-wrap center-overview-table"
                    :class="{ 'center-overview-table--scroll': centerOverviewRuns.length > CENTER_OVERVIEW_SCROLL_ROWS }"
                  >
                    <table class="grid-table mini">
                      <thead>
                        <tr>
                          <th style="width:80px">运行</th>
                          <th>流程</th>
                          <th style="width:110px">状态</th>
                          <th style="width:120px">耗时</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-if="loadingCenterOverviewRuns"><td colspan="4" class="muted center">加载中…</td></tr>
                        <tr v-else-if="centerOverviewRuns.length === 0"><td colspan="4" class="muted center">近 24 小时无运行记录</td></tr>
                        <tr
                          v-for="r in centerOverviewRuns"
                          :key="r.id"
                          class="clickable"
                          @click="openRunFromCenterOverview(r.id)"
                        >
                          <td class="mono">#{{ r.id }}</td>
                          <td class="ov-cell-ellipsis" :title="`${flowLabelById(r.flow_code)} v${r.ver_no}`">{{ flowLabelById(r.flow_code) }} · v{{ r.ver_no }}</td>
                          <td><span class="tag" :class="runStatusTag(r.status)">{{ runStatusLabel(r.status) }}</span></td>
                          <td class="mono small">{{ runElapsed(r) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div class="ov-pager">
                    <span class="muted small">共 {{ centerOverviewRunsTotal }} 条 · 第 {{ centerOverviewRunsPage }} 页</span>
                    <button type="button" class="btn small ghost" :disabled="centerOverviewRunsOffset === 0 || loadingCenterOverviewRuns" @click="centerOverviewRunsPrev">上一页</button>
                    <button type="button" class="btn small ghost" :disabled="!centerOverviewRunsHasNext || loadingCenterOverviewRuns" @click="centerOverviewRunsNext">下一页</button>
                  </div>
                </article>

                <article class="ov-card">
                  <div class="ov-head">
                    <div class="ov-head-main">
                      <div class="ov-title">最近失败运行</div>
                      <span class="muted small">近 {{ CENTER_OVERVIEW_LOOKBACK_HOURS }} 小时 · 每部署最新一条</span>
                    </div>
                    <button type="button" class="btn small ghost" @click="openRunsTab()">打开运行记录</button>
                  </div>
                  <div
                    class="ov-table-wrap center-overview-table"
                    :class="{ 'center-overview-table--scroll': centerOverviewFailedRuns.length > CENTER_OVERVIEW_SCROLL_ROWS }"
                  >
                    <table class="grid-table mini">
                      <thead>
                        <tr>
                          <th style="width:100px">部署</th>
                          <th style="width:80px">运行</th>
                          <th style="width:28%">流程</th>
                          <th>错误</th>
                          <th style="width:140px">失败时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-if="loadingCenterOverviewFailedRuns"><td colspan="5" class="muted center">加载中…</td></tr>
                        <tr v-else-if="centerOverviewFailedRuns.length === 0"><td colspan="5" class="muted center">近 24 小时无失败运行</td></tr>
                        <tr
                          v-for="r in centerOverviewFailedRuns"
                          :key="r.id"
                          class="clickable"
                          @click="openRunFromCenterOverview(r.id)"
                        >
                          <td class="mono small ov-cell-ellipsis" :title="deploymentOverviewFlowLabel(r.deployment_id)">{{ deploymentOverviewFlowLabel(r.deployment_id) }}</td>
                          <td class="mono">#{{ r.id }}</td>
                          <td class="ov-cell-ellipsis" :title="`${flowLabelById(r.flow_code)} v${r.ver_no}`">{{ flowLabelById(r.flow_code) }} · v{{ r.ver_no }}</td>
                          <td class="ov-cell-ellipsis bad" :title="r.error || undefined">{{ truncateText(r.error, 80) }}</td>
                          <td class="mono small ov-cell-ellipsis">{{ formatTs(r.finished_at || r.started_at) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div class="ov-pager">
                    <span class="muted small">共 {{ centerOverviewFailedRunsTotal }} 条 · 第 {{ centerOverviewFailedRunsPage }} 页</span>
                    <button type="button" class="btn small ghost" :disabled="centerOverviewFailedRunsOffset === 0 || loadingCenterOverviewFailedRuns" @click="centerOverviewFailedRunsPrev">上一页</button>
                    <button type="button" class="btn small ghost" :disabled="!centerOverviewFailedRunsHasNext || loadingCenterOverviewFailedRuns" @click="centerOverviewFailedRunsNext">下一页</button>
                  </div>
                </article>
              </div>

              <article class="ov-card ov-card--wide">
                <div class="ov-head">
                  <div class="ov-head-main">
                    <div class="ov-title">最近失败消息</div>
                    <span class="muted small">近 {{ CENTER_OVERVIEW_LOOKBACK_HOURS }} 小时 · 每部署最新一条</span>
                  </div>
                </div>
                <div
                  class="ov-table-wrap center-overview-table"
                  :class="{ 'center-overview-table--scroll': centerOverviewFailedMessages.length > CENTER_OVERVIEW_SCROLL_ROWS }"
                >
                  <table class="grid-table mini">
                    <thead>
                      <tr>
                        <th style="width:100px">部署</th>
                        <th style="width:160px">位置</th>
                        <th>错误</th>
                        <th style="width:128px">更新时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="loadingCenterOverviewFailedMessages"><td colspan="4" class="muted center">加载中…</td></tr>
                      <tr v-else-if="centerOverviewFailedMessages.length === 0"><td colspan="4" class="muted center">近 24 小时无失败消息</td></tr>
                      <tr
                        v-for="m in centerOverviewFailedMessages"
                        :key="m.id"
                        class="clickable"
                        @click="openFailedMessageFromCenterOverview(m)"
                      >
                        <td class="mono small ov-cell-ellipsis" :title="deploymentOverviewFlowLabel(m.deployment_id)">{{ deploymentOverviewFlowLabel(m.deployment_id) }}</td>
                        <td class="mono small ov-cell-ellipsis" :title="`${m.topic} p${m.partition} o${m.offset}`">{{ m.topic }} · p{{ m.partition }} · o{{ m.offset }}</td>
                        <td class="ov-cell-ellipsis bad" :title="m.error || undefined">{{ truncateText(m.error, 80) }}</td>
                        <td class="mono small ov-cell-ellipsis">{{ formatTs(m.updated_at) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="ov-pager">
                  <span class="muted small">共 {{ centerOverviewFailedMessagesTotal }} 条 · 第 {{ centerOverviewFailedMessagesPage }} 页</span>
                  <button type="button" class="btn small ghost" :disabled="centerOverviewFailedMessagesOffset === 0 || loadingCenterOverviewFailedMessages" @click="centerOverviewFailedMessagesPrev">上一页</button>
                  <button type="button" class="btn small ghost" :disabled="!centerOverviewFailedMessagesHasNext || loadingCenterOverviewFailedMessages" @click="centerOverviewFailedMessagesNext">下一页</button>
                </div>
              </article>
            </div>
          </section>

          <DeploymentCreateForm
            v-else-if="depWorkspace === 'create'"
            ref="deployCreateFormRef"
            :flow-options="flowOptions"
            :profile-options="profileOptions"
            :workers="workers"
            :active-workers="activeWorkers"
            :worker-status-class="workerStatusClass"
            :external-error="formError"
            @cancel="openDeployOverview()"
            @created="onDeploymentCreated"
            @error="(msg) => { formError = msg; }"
          />

          <DeploymentCreateForm
            v-else-if="depWorkspace === 'edit' && selectedDeployment"
            ref="deployEditFormRef"
            :edit-deployment="selectedDeployment"
            :flow-options="flowOptions"
            :profile-options="profileOptions"
            :workers="workers"
            :active-workers="activeWorkers"
            :worker-status-class="workerStatusClass"
            :external-error="formError"
            @cancel="closeEditForm()"
            @saved="onDeploymentSaved"
            @error="(msg) => { formError = msg; }"
            @request-stop="requestStopDeployment(selectedDeployment.id)"
          />

          <!-- 部署详情加载中 -->
          <section
            v-else-if="depWorkspace === 'detail' && selectedDeploymentId != null && !selectedDeployment"
            class="panel dep-detail-loading"
          >
            <p class="muted center pad">加载部署详情…</p>
          </section>

          <!-- 部署详情工作台 -->
          <section v-else-if="selectedDeployment && depWorkspace === 'detail'" class="panel">
            <header class="panel-head">
              <div class="panel-head-text">
                <div class="panel-title dep-detail-title">
                  <span class="mono dep-detail-id">#{{ selectedDeployment.id }}</span>
                  <span class="dep-detail-flow">{{ flowLabelById(selectedDeployment.flow_code) }}</span>
                  <span class="dep-detail-ver">v{{ selectedDeployment.ver_no }}</span>
                  <span class="tag dep-status-tag" :class="statusTag(selectedDeployment.status)">
                    {{ deploymentStatusLabel(selectedDeployment.status) }}
                  </span>
                </div>
                <div class="muted small dep-detail-sub">
                  <span class="dep-mode" :class="deploymentModeMod(selectedDeployment.mode)">
                    {{ deploymentModeLabel(selectedDeployment.mode) }}
                  </span>
                  <span class="dep-detail-sub-sep" aria-hidden="true">·</span>
                  <span>{{ deploymentScheduleSubtitle(selectedDeployment, subSummary) }}</span>
                  <span v-if="selectedDeployment.updated_at">
                    · 更新 <span class="mono">{{ formatTs(selectedDeployment.updated_at) }}</span>
                  </span>
                </div>
              </div>
              <div class="panel-actions">
                <button
                  type="button"
                  class="btn ghost small"
                  :disabled="!isDeploymentConfigEditable(selectedDeployment.status)"
                  :title="deploymentEditLockHint(selectedDeployment.status)"
                  @click="openEditDeployment()"
                >编辑</button>
                <button
                  v-if="selectedDeployment.status === 'running'"
                  type="button"
                  class="btn warn small"
                  @click="requestStopDeployment(selectedDeployment.id)"
                >停止</button>
                <button
                  v-else-if="selectedDeployment.status === 'stopped'"
                  type="button"
                  class="btn primary small"
                  @click="requestStartDeployment(selectedDeployment.id)"
                >启动</button>
                <button
                  v-else-if="selectedDeployment.status === 'stopping' || selectedDeployment.status === 'failed'"
                  type="button"
                  class="btn ghost small"
                  @click="requestRestartDeployment(selectedDeployment.id)"
                >重启</button>
                <div class="dep-action-menu-wrap" @click.stop>
                  <button
                    type="button"
                    class="btn ghost small"
                    aria-label="更多"
                    title="更多"
                    aria-haspopup="menu"
                    :aria-expanded="depDetailMenuOpen"
                    @click="toggleDepDetailMenu()"
                  >⋯</button>
                  <div v-if="depDetailMenuOpen" class="menu" role="menu">
                    <button
                      type="button"
                      class="menu-item"
                      role="menuitem"
                      @click="closeDepMenu(); copyDeploymentSummary(selectedDeployment)"
                    >复制</button>
                    <button
                      type="button"
                      class="menu-item danger"
                      role="menuitem"
                      @click="closeDepMenu(); removeDeployment(selectedDeployment.id)"
                    >删除</button>
                  </div>
                </div>
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
              <button type="button" class="seg jump" @click="viewRuns(selectedDeployment, { forceGlobal: true })">
                全局运行页 <span class="jump-ico" aria-hidden="true">↗</span>
              </button>
            </nav>

            <section v-if="depDetailTab === 'overview'" class="panel-body">
              <DeploymentDetailOverview
                :deployment="selectedDeployment"
                :sub-summary="subSummary"
                :runs-preview="depOverviewRunsPreview"
                :runs-preview-total="depOverviewRunsTotal"
                :workers="workers"
                :loading-sub-summary="loadingSubSummary"
                :loading-runs-preview="loadingDepOverviewRuns"
                :format-ts="formatTs"
                :run-elapsed="runElapsed"
                @navigate-tab="onOverviewNavigateTab"
                @navigate-workers="switchTab('workers')"
                @open-run="openOverviewRun"
                @open-message="openSubscriptionMessage"
              />
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
                >{{ messageStatusLabel('processing') }}</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === 'completed' }"
                  @click="depMessagesStatusFilter = 'completed'; depMessagesOffset = 0; loadSubscriptionMessages()"
                >{{ messageStatusLabel('completed') }}</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depMessagesStatusFilter === 'failed' }"
                  @click="depMessagesStatusFilter = 'failed'; depMessagesOffset = 0; loadSubscriptionMessages()"
                >{{ messageStatusLabel('failed') }}</button>
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
                    <td><span class="tag small" :class="messageStatusTag(m.status)">{{ messageStatusLabel(m.status) }}</span></td>
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
                >{{ runStatusLabel('running') }}</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'failed' }"
                  @click="depRunsStatusFilter='failed'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >{{ runStatusLabel('failed') }}</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'completed' }"
                  @click="depRunsStatusFilter='completed'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >{{ runStatusLabel('completed') }}</button>
                <button
                  type="button"
                  class="chip"
                  :class="{ active: depRunsStatusFilter === 'terminated' }"
                  @click="depRunsStatusFilter='terminated'; depRunsOffset=0; loadEmbeddedDepRuns()"
                >{{ runStatusLabel('terminated') }}</button>
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
                    <th style="width:80px">运行模式</th>
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
                    <td><span class="tag" :class="runStatusTag(r.status)">{{ runStatusLabel(r.status) }}</span></td>
                    <td><span class="tag mode">{{ runModeLabel(r.mode) }}</span></td>
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
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import {
  deleteDeployment,
  getDeployment,
  isDeploymentConfigEditable,
  listDeployments,
  patchDeployment,
  type Deployment,
  type DeploymentDetail,
} from "@/api/deployments";
import { listWorkers, type Worker } from "@/api/workers";
import {
  getDeployRun,
  listDeployRuns,
  listRecentOverviewDeployRuns,
  listRecentFailedDeployRuns,
} from "@/api/deployRuns";
import {
  getSubscriptionSummary,
  listRecentFailedSubscriptionMessages,
  listSubscriptionMessages,
  type SubscriptionMessageRow,
  type SubscriptionMessagesListResponse,
  type SubscriptionSummary,
} from "@/api/subscriptionObservability";
import type { FlowRunDetail, FlowRunSummary, FlowRunsListResponse } from "@/api/flowRuns";
import { useFlowLabels } from "@/composables/useFlowLabels";
import { fetchProfiles } from "@/api/profiles";
import RunDetailDrawer from "@/components/RunDetailDrawer.vue";
import DeploymentCreateForm from "@/components/DeploymentCreateForm.vue";
import DeploymentDetailOverview from "@/components/ops/DeploymentDetailOverview.vue";
import {
  deploymentModeLabel,
  deploymentListItemMod,
  deploymentModeMod,
  deploymentScheduleSubtitle,
  deploymentStatusLabel,
  messageStatusLabel,
  runModeLabel,
  runStatusLabel,
  scheduleTypeLabel,
  workerStatusLabel,
} from "@/utils/deploymentOverview";

type TabId = "overview" | "deployments" | "runs" | "workers";
type DepDetailTabId = "overview" | "messages" | "runs";

const OPS_CENTER_STATE_KEY = "flowEngine:ops:centerState";

type OpsCenterPersistedState = {
  tab: TabId;
  depSelection: "overview" | number;
  depDetailTab: DepDetailTabId;
};

const OPS_ALLOWED_TABS = new Set<TabId>(["overview", "deployments", "runs", "workers"]);
const OPS_ALLOWED_DETAIL_TABS = new Set<DepDetailTabId>(["overview", "messages", "runs"]);

function readStoredOpsCenterState(): OpsCenterPersistedState | null {
  try {
    const raw = localStorage.getItem(OPS_CENTER_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<OpsCenterPersistedState>;
    if (!parsed.tab || !OPS_ALLOWED_TABS.has(parsed.tab)) return null;
    const depSelection =
      parsed.depSelection === "overview"
        ? "overview"
        : typeof parsed.depSelection === "number"
            && Number.isInteger(parsed.depSelection)
            && parsed.depSelection > 0
          ? parsed.depSelection
          : "overview";
    const depDetailTab =
      parsed.depDetailTab && OPS_ALLOWED_DETAIL_TABS.has(parsed.depDetailTab)
        ? parsed.depDetailTab
        : "overview";
    return { tab: parsed.tab, depSelection, depDetailTab };
  } catch {
    return null;
  }
}

function writeStoredOpsCenterState(state: OpsCenterPersistedState) {
  try {
    localStorage.setItem(OPS_CENTER_STATE_KEY, JSON.stringify(state));
  } catch {
    /* private mode / denied */
  }
}

const storedOpsCenterState = readStoredOpsCenterState();

const TABS: { id: TabId; label: string }[] = [
  { id: "deployments", label: "部署管理" },
  { id: "runs", label: "运行记录" },
  { id: "workers", label: "工作节点" },
];

const tab = ref<TabId>(storedOpsCenterState?.tab ?? "deployments");
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
const initialStoredDeploymentId =
  storedOpsCenterState?.tab === "deployments"
  && storedOpsCenterState.depSelection !== "overview"
  && typeof storedOpsCenterState.depSelection === "number"
    ? storedOpsCenterState.depSelection
    : null;

const selectedDeploymentId = ref<number | null>(initialStoredDeploymentId);
const selectedDeployment = ref<DeploymentDetail | null>(null);
const depDetailTab = ref<DepDetailTabId>(storedOpsCenterState?.depDetailTab ?? "overview");
const DEP_CENTER_OVERVIEW_LABEL = "总概览";
const CENTER_OVERVIEW_PAGE_SIZE = 10;
const CENTER_OVERVIEW_SCROLL_ROWS = 5;
const CENTER_OVERVIEW_LOOKBACK_HOURS = 24;

const depWorkspace = ref<"overview" | "create" | "detail" | "edit">(
  initialStoredDeploymentId != null ? "detail" : "overview",
);

const centerOverviewRuns = ref<FlowRunSummary[]>([]);
const centerOverviewRunsOffset = ref(0);
const centerOverviewRunsTotal = ref(0);
const loadingCenterOverviewRuns = ref(false);
const centerOverviewFailedRuns = ref<FlowRunSummary[]>([]);
const centerOverviewFailedRunsOffset = ref(0);
const centerOverviewFailedRunsTotal = ref(0);
const loadingCenterOverviewFailedRuns = ref(false);
const centerOverviewFailedMessages = ref<SubscriptionMessageRow[]>([]);
const centerOverviewFailedMessagesOffset = ref(0);
const centerOverviewFailedMessagesTotal = ref(0);
const loadingCenterOverviewFailedMessages = ref(false);

const centerOverviewRunsPage = computed(
  () => Math.floor(centerOverviewRunsOffset.value / CENTER_OVERVIEW_PAGE_SIZE) + 1,
);
const centerOverviewFailedRunsPage = computed(
  () => Math.floor(centerOverviewFailedRunsOffset.value / CENTER_OVERVIEW_PAGE_SIZE) + 1,
);
const centerOverviewFailedMessagesPage = computed(
  () => Math.floor(centerOverviewFailedMessagesOffset.value / CENTER_OVERVIEW_PAGE_SIZE) + 1,
);
const centerOverviewRunsHasNext = computed(
  () => centerOverviewRunsOffset.value + centerOverviewRuns.value.length < centerOverviewRunsTotal.value,
);
const centerOverviewFailedRunsHasNext = computed(
  () =>
    centerOverviewFailedRunsOffset.value + centerOverviewFailedRuns.value.length
    < centerOverviewFailedRunsTotal.value,
);
const centerOverviewFailedMessagesHasNext = computed(
  () =>
    centerOverviewFailedMessagesOffset.value + centerOverviewFailedMessages.value.length
    < centerOverviewFailedMessagesTotal.value,
);

// Deployment detail header "more" menu
const depDetailMenuOpen = ref(false);

function toggleDepDetailMenu() {
  depDetailMenuOpen.value = !depDetailMenuOpen.value;
}

function closeDepMenu() {
  depDetailMenuOpen.value = false;
}

function onDocPointerDown(e: PointerEvent) {
  if (!depDetailMenuOpen.value) return;
  const t = e.target as Node | null;
  const el = t instanceof Element ? t : null;
  if (!el || !el.closest(".dep-action-menu-wrap")) {
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
const depOverviewRunsPreview = ref<FlowRunSummary[]>([]);
const depOverviewRunsTotal = ref(0);
const loadingDepOverviewRuns = ref(false);
const DEP_OVERVIEW_RUNS_PREVIEW_LIMIT = 5;
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

const formError = ref("");
const deployCreateFormRef = ref<InstanceType<typeof DeploymentCreateForm> | null>(null);
const deployEditFormRef = ref<InstanceType<typeof DeploymentCreateForm> | null>(null);
const { flowOptions, ensureFlowList, flowLabelById, flowListItemLabel } = useFlowLabels();

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

function closeGlobalRunDrawer() {
  selectedRunId.value = null;
  selectedRunDetail.value = null;
  loadingRunDetail.value = false;
}

function openRunsTab() {
  closeGlobalRunDrawer();
  switchTab("runs");
}

function openRunFromCenterOverview(runId: number) {
  closeGlobalRunDrawer();
  switchTab("runs");
  void selectRun(runId);
}

async function selectDeployment(
  id: number,
  opts?: { detailTab?: DepDetailTabId },
) {
  closeGlobalRunDrawer();
  closeDepMenu();
  if (tab.value !== "deployments") {
    tab.value = "deployments";
  }
  selectedDeploymentId.value = id;
  depDetailTab.value = opts?.detailTab ?? "overview";
  depWorkspace.value = "detail";
  depRunsOffset.value = 0;
  depRunsResp.value = null;
  selectedDepRunId.value = null;
  selectedDepRunDetail.value = null;
  subSummary.value = null;
  subMessagesResp.value = null;
  depMessagesOffset.value = 0;
  depOverviewRunsPreview.value = [];
  depOverviewRunsTotal.value = 0;
  if (selectedDeployment.value?.id !== id) {
    selectedDeployment.value = null;
  }
  try {
    selectedDeployment.value = await getDeployment(id);
    await loadDeploymentOverviewData(id);
    if (depDetailTab.value === "messages") {
      await loadSubscriptionMessages();
    } else if (depDetailTab.value === "runs") {
      await loadEmbeddedDepRuns();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    if (selectedDeploymentId.value === id) {
      selectedDeploymentId.value = null;
      depWorkspace.value = "overview";
    }
  }
}

async function loadDepOverviewRunsPreview(deploymentId: number) {
  loadingDepOverviewRuns.value = true;
  try {
    const res = await listDeployRuns({
      deployment_id: deploymentId,
      offset: 0,
      limit: DEP_OVERVIEW_RUNS_PREVIEW_LIMIT,
    });
    depOverviewRunsPreview.value = res.runs;
    depOverviewRunsTotal.value = res.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingDepOverviewRuns.value = false;
  }
}

async function loadDeploymentOverviewData(deploymentId: number) {
  const d = selectedDeployment.value;
  const tasks: Promise<void>[] = [loadDepOverviewRunsPreview(deploymentId)];
  if (d?.schedule_type === "subscription") {
    tasks.push(loadSubscriptionSummary());
  }
  await Promise.all(tasks);
}

async function refreshDeploymentOverview() {
  const id = selectedDeploymentId.value;
  if (id == null) return;
  try {
    selectedDeployment.value = await getDeployment(id);
    await loadDeploymentOverviewData(id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function onOverviewNavigateTab(nextTab: DepDetailTabId) {
  depDetailTab.value = nextTab;
  if (nextTab === "messages") {
    depMessagesOffset.value = 0;
    void loadSubscriptionMessages();
  } else if (nextTab === "runs") {
    depRunsOffset.value = 0;
    void loadEmbeddedDepRuns();
  }
}

async function openOverviewRun(runId: number) {
  depDetailTab.value = "runs";
  depRunsOffset.value = 0;
  await loadEmbeddedDepRuns();
  await selectEmbeddedDepRun(runId);
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
        openDeployOverview();
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

async function ensureProfileOptions(includeCode?: string): Promise<void> {
  if (profileOptions.value.length === 0) {
    try {
      const res = await fetchProfiles();
      profileOptions.value = res.profiles;
    } catch {
      // best effort
    }
  }
  const code = includeCode?.trim();
  if (code && !profileOptions.value.includes(code)) {
    profileOptions.value = [code, ...profileOptions.value];
  }
}

async function openCreateForm() {
  if (tab.value !== "deployments") switchTab("deployments");
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
  await ensureProfileOptions();
  if (workers.value.length === 0) {
    try {
      await loadWorkers();
    } catch {
      // ignore; create form still usable without workers list
    }
  }
}

function deploymentOverviewFlowLabel(deploymentId: number | null | undefined): string {
  if (deploymentId == null) return "—";
  const d = deployments.value.find((x) => x.id === deploymentId);
  if (d) return `${flowLabelById(d.flow_code)} #${d.id}`;
  return `#${deploymentId}`;
}

function resetCenterOverviewPagination() {
  centerOverviewRunsOffset.value = 0;
  centerOverviewFailedRunsOffset.value = 0;
  centerOverviewFailedMessagesOffset.value = 0;
}

async function loadCenterOverviewRecentRuns() {
  loadingCenterOverviewRuns.value = true;
  try {
    await ensureFlowList();
    const res = await listRecentOverviewDeployRuns({
      hours: CENTER_OVERVIEW_LOOKBACK_HOURS,
      offset: centerOverviewRunsOffset.value,
      limit: CENTER_OVERVIEW_PAGE_SIZE,
    });
    centerOverviewRuns.value = res.runs;
    centerOverviewRunsTotal.value = res.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingCenterOverviewRuns.value = false;
  }
}

async function loadCenterOverviewFailedRuns() {
  loadingCenterOverviewFailedRuns.value = true;
  try {
    await ensureFlowList();
    const res = await listRecentFailedDeployRuns({
      hours: CENTER_OVERVIEW_LOOKBACK_HOURS,
      offset: centerOverviewFailedRunsOffset.value,
      limit: CENTER_OVERVIEW_PAGE_SIZE,
    });
    centerOverviewFailedRuns.value = res.runs;
    centerOverviewFailedRunsTotal.value = res.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingCenterOverviewFailedRuns.value = false;
  }
}

async function loadCenterOverviewFailedMessages() {
  loadingCenterOverviewFailedMessages.value = true;
  try {
    await ensureFlowList();
    const res = await listRecentFailedSubscriptionMessages({
      hours: CENTER_OVERVIEW_LOOKBACK_HOURS,
      offset: centerOverviewFailedMessagesOffset.value,
      limit: CENTER_OVERVIEW_PAGE_SIZE,
    });
    centerOverviewFailedMessages.value = res.messages;
    centerOverviewFailedMessagesTotal.value = res.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loadingCenterOverviewFailedMessages.value = false;
  }
}

async function loadCenterOverviewRuns() {
  await Promise.all([
    loadCenterOverviewRecentRuns(),
    loadCenterOverviewFailedRuns(),
    loadCenterOverviewFailedMessages(),
  ]);
}

function centerOverviewRunsPrev() {
  centerOverviewRunsOffset.value = Math.max(
    0,
    centerOverviewRunsOffset.value - CENTER_OVERVIEW_PAGE_SIZE,
  );
  void loadCenterOverviewRecentRuns();
}

function centerOverviewRunsNext() {
  if (!centerOverviewRunsHasNext.value) return;
  centerOverviewRunsOffset.value += CENTER_OVERVIEW_PAGE_SIZE;
  void loadCenterOverviewRecentRuns();
}

function centerOverviewFailedRunsPrev() {
  centerOverviewFailedRunsOffset.value = Math.max(
    0,
    centerOverviewFailedRunsOffset.value - CENTER_OVERVIEW_PAGE_SIZE,
  );
  void loadCenterOverviewFailedRuns();
}

function centerOverviewFailedRunsNext() {
  if (!centerOverviewFailedRunsHasNext.value) return;
  centerOverviewFailedRunsOffset.value += CENTER_OVERVIEW_PAGE_SIZE;
  void loadCenterOverviewFailedRuns();
}

function centerOverviewFailedMessagesPrev() {
  centerOverviewFailedMessagesOffset.value = Math.max(
    0,
    centerOverviewFailedMessagesOffset.value - CENTER_OVERVIEW_PAGE_SIZE,
  );
  void loadCenterOverviewFailedMessages();
}

function centerOverviewFailedMessagesNext() {
  if (!centerOverviewFailedMessagesHasNext.value) return;
  centerOverviewFailedMessagesOffset.value += CENTER_OVERVIEW_PAGE_SIZE;
  void loadCenterOverviewFailedMessages();
}

async function openFailedMessageFromCenterOverview(m: SubscriptionMessageRow) {
  const depId = m.deployment_id;
  if (depId == null) return;
  await selectDeployment(depId);
  depDetailTab.value = "messages";
  depMessagesStatusFilter.value = "failed";
  depMessagesOffset.value = 0;
  await loadSubscriptionMessages();
}

function openDeployOverview() {
  closeGlobalRunDrawer();
  if (tab.value !== "deployments") {
    tab.value = "deployments";
  }
  depWorkspace.value = "overview";
  selectedDeploymentId.value = null;
  selectedDeployment.value = null;
  depDetailTab.value = "overview";
  closeDepMenu();
  if (deployments.value.length === 0) void loadDeployments();
  if (workers.value.length === 0) void loadWorkers();
  resetCenterOverviewPagination();
  void loadCenterOverviewRuns();
}

async function onDeploymentCreated(id: number) {
  formError.value = "";
  await loadDeployments();
  selectDeployment(id);
}

function deploymentEditLockHint(status: string): string {
  if (isDeploymentConfigEditable(status)) return "";
  if (status === "running") return "运行中的部署须先停止后方可编辑";
  if (status === "stopping") return "部署正在停止中，请等待完成后再编辑";
  if (status === "pending") return "部署正在调度/启动中，请先停止后再编辑";
  return "请先停止部署后再编辑";
}

function deploymentListMetaRest(d: Deployment): string {
  const parts: string[] = [scheduleTypeLabel(String(d.schedule_type))];
  const env = d.env_profile_code?.trim();
  if (env) parts.push(env);
  if (d.schedule_type === "cron" && d.schedule_config?.cron_expr) {
    parts.push(d.schedule_config.cron_expr);
  }
  return parts.join(" · ");
}

function deploymentListItemTitle(d: Deployment): string {
  const mode = deploymentModeLabel(d.mode);
  const meta = deploymentListMetaRest(d);
  const when = formatRelative(d.updated_at || d.created_at);
  return `${flowLabelById(d.flow_code)} v${d.ver_no} · #${d.id} · ${mode} · ${meta} · ${when}`;
}

function copyDeploymentSummary(d: Deployment | DeploymentDetail) {
  void copyText(
    JSON.stringify(
      {
        id: d.id,
        flow_code: d.flow_code,
        ver_no: d.ver_no,
        mode: d.mode,
        schedule_type: d.schedule_type,
        cron_expr: d.schedule_type === "cron" ? d.schedule_config?.cron_expr : undefined,
        status: d.status,
        env_profile_code: d.env_profile_code || "",
        updated_at: d.updated_at,
        created_at: d.created_at,
      },
      null,
      2,
    ),
  );
}

async function openEditDeployment() {
  if (!selectedDeployment.value) return;
  if (!isDeploymentConfigEditable(selectedDeployment.value.status)) return;
  formError.value = "";
  const dep = selectedDeployment.value;
  try {
    await ensureFlowList();
    await ensureProfileOptions(dep.env_profile_code);
  } catch (e) {
    formError.value = e instanceof Error ? e.message : String(e);
  }
  depWorkspace.value = "edit";
  closeDepMenu();
  await nextTick();
  await deployEditFormRef.value?.loadFromDeployment(dep);
}

function closeEditForm() {
  if (selectedDeploymentId.value != null) {
    depWorkspace.value = "detail";
    depDetailTab.value = "overview";
  } else {
    openDeployOverview();
  }
}

async function onDeploymentSaved(id: number) {
  formError.value = "";
  await loadDeployments();
  await selectDeployment(id);
  depWorkspace.value = "detail";
  depDetailTab.value = "overview";
}

watch(
  () => selectedDeployment.value?.status,
  (st) => {
    if (depWorkspace.value !== "edit" || !selectedDeployment.value || st == null) return;
    if (isDeploymentConfigEditable(String(st))) {
      void deployEditFormRef.value?.loadFromDeployment(selectedDeployment.value);
    }
  },
);

let ingressRetryPollTimer: ReturnType<typeof setInterval> | null = null;

function clearIngressRetryPoll() {
  if (ingressRetryPollTimer != null) {
    clearInterval(ingressRetryPollTimer);
    ingressRetryPollTimer = null;
  }
}

watch(
  () => selectedDeployment.value?.status_detail?.reason,
  (reason) => {
    clearIngressRetryPoll();
    if (reason !== "subscription_ingress_retrying" || selectedDeploymentId.value == null) return;
    ingressRetryPollTimer = setInterval(() => {
      void refreshDeploymentOverview();
      void loadDeployments();
    }, 5000);
  },
  { immediate: true },
);

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
  // 运行中心只展示部署运行记录，测试运行已在数据层隔离。
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

function snapshotOpsCenterState(): OpsCenterPersistedState {
  const depSelection: "overview" | number =
    tab.value === "deployments"
    && depWorkspace.value === "detail"
    && selectedDeploymentId.value != null
      ? selectedDeploymentId.value
      : "overview";

  return {
    tab: tab.value,
    depSelection,
    depDetailTab: depDetailTab.value,
  };
}

function persistOpsCenterState() {
  if (depWorkspace.value === "create" || depWorkspace.value === "edit") return;
  writeStoredOpsCenterState(snapshotOpsCenterState());
}

async function hydrateOpsCenterState() {
  if (!storedOpsCenterState) {
    if (tab.value === "deployments") {
      openDeployOverview();
    } else {
      switchTab(tab.value);
    }
    return;
  }

  if (storedOpsCenterState.tab !== "deployments") {
    switchTab(storedOpsCenterState.tab);
    return;
  }

  if (typeof storedOpsCenterState.depSelection === "number") {
    await loadDeployments();
    if (deployments.value.some((d) => d.id === storedOpsCenterState.depSelection)) {
      await selectDeployment(storedOpsCenterState.depSelection, {
        detailTab: storedOpsCenterState.depDetailTab,
      });
    } else {
      openDeployOverview();
    }
  } else {
    openDeployOverview();
  }
}

// ---------------- Helpers ----------------

function switchTab(id: TabId) {
  if (tab.value === "runs" && id !== "runs") {
    closeGlobalRunDrawer();
  }
  tab.value = id;
  if (id === "deployments" && deployments.value.length === 0) loadDeployments();
  if (id === "runs") {
    if (depWorkspace.value === "overview") closeGlobalRunDrawer();
    loadRuns();
  }
  if (id === "workers" && workers.value.length === 0) loadWorkers();
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

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown, true);
  void ensureFlowList();
  void hydrateOpsCenterState();
});

watch([tab, selectedDeploymentId, depWorkspace, depDetailTab], persistOpsCenterState);

onUnmounted(() => {
  document.removeEventListener("pointerdown", onDocPointerDown, true);
  clearIngressRetryPoll();
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
  gap: 12px;
}

.top-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
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
  border-radius: 6px 6px 0 0;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  color: var(--muted);
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    background 0.15s ease;
}

.tab:hover:not(.active) {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.tab:focus {
  outline: none;
}

.tab:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  outline-offset: 2px;
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

.center-overview-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.center-overview-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.ov-card--wide {
  width: 100%;
}

.dep-sub-workspace {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.panel-head-text {
  min-width: 0;
  flex: 1;
}

.dep-overview-back {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-top: 1px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
}

.dep-overview-back:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 50%, var(--surface));
}

.dep-overview-back:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  outline-offset: 2px;
}

.dep-overview-back.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 55%, var(--surface));
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
  flex-wrap: wrap;
}

.ov-head .ov-head-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
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

.center-overview-runs-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.center-overview-table .grid-table.mini {
  table-layout: fixed;
  width: 100%;
}

.center-overview-table .ov-cell-ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 1px;
}

.center-overview-table--scroll {
  max-height: calc(34px + 33px * 5);
}

.ov-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

@media (max-width: 980px) {
  .center-overview-stats {
    grid-template-columns: 1fr;
  }

  .center-overview-runs-row {
    grid-template-columns: 1fr;
  }

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
  background: var(--surface);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
  font-weight: 500;
  font-family: inherit;
  color: var(--muted);
  cursor: pointer;
  box-shadow: var(--shadow);
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease;
}

.chip:hover:not(.active) {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 45%, var(--surface));
  color: var(--text);
}

.chip:focus {
  outline: none;
}

.chip:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  outline-offset: 2px;
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

/* Deployment mode (生产/灰度) — square type label, not lifecycle status pill */
.dep-mode {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.25;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 50%, var(--surface));
  color: var(--muted);
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

.dep-mode--production {
  border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 75%, var(--surface));
  color: color-mix(in srgb, var(--accent) 72%, #0f172a);
  font-weight: 600;
}

.dep-mode--shadow {
  border-color: color-mix(in srgb, #f59e0b 40%, var(--border));
  background: color-mix(in srgb, #fffbeb 88%, var(--surface));
  color: #92400e;
  font-weight: 500;
}

.dep-mode--compact {
  padding: 1px 5px;
  font-size: 9px;
  border-radius: 3px;
}

.dep-detail-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  width: 100%;
}

.dep-detail-id {
  font-weight: 800;
}

.dep-detail-flow {
  font-weight: 700;
  min-width: 0;
}

.dep-detail-ver {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.dep-status-tag {
  flex-shrink: 0;
  text-transform: none;
  letter-spacing: 0.01em;
}

.dep-detail-sub {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  line-height: 1.45;
}

.dep-detail-sub-sep {
  color: color-mix(in srgb, var(--muted) 70%, transparent);
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
  border-left-width: 3px;
  border-radius: 10px;
  padding: 7px 9px 7px 8px;
  background: var(--surface);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    border-left-width 0.12s ease,
    box-shadow 0.15s ease;
}

.dep2-item.active {
  border-left-width: 5px;
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent);
}

/* 生产：左边框随状态加深 — 默认最淡 / 悬停略深 / 选中最鲜明 */
.dep2-item--production {
  border-left-color: color-mix(in srgb, var(--accent) 28%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 28%, var(--surface));
}

.dep2-item--production:hover:not(.active) {
  border-left-color: color-mix(in srgb, var(--accent) 62%, #1e40af);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 48%, var(--surface));
}

.dep2-item--production.active {
  border-left-width: 5px;
  border-left-color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
  background: var(--accent-soft);
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent),
    0 1px 3px color-mix(in srgb, var(--accent) 14%, transparent);
}

/* 灰度：左边框随状态加深 — 默认最淡 / 悬停略深 / 选中最鲜明 */
.dep2-item--shadow {
  border-left-color: color-mix(in srgb, #fbbf24 38%, var(--border));
  background: color-mix(in srgb, #fffbeb 40%, var(--surface));
}

.dep2-item--shadow:hover:not(.active) {
  border-left-color: #fbbf24;
  border-color: color-mix(in srgb, #f59e0b 24%, var(--border));
  background: color-mix(in srgb, #fef3c7 52%, var(--surface));
}

.dep2-item--shadow.active {
  border-left-width: 5px;
  border-left-color: #d97706;
  border-color: color-mix(in srgb, #f59e0b 42%, var(--border));
  background: #fef3c7;
  box-shadow:
    0 0 0 2px color-mix(in srgb, #f59e0b 24%, transparent),
    0 1px 3px color-mix(in srgb, #d97706 12%, transparent);
}

.dep2-item.active .dep2-flow {
  font-weight: 800;
}

.dep2-item--production.active .dep2-flow {
  color: var(--accent);
}

.dep2-item--shadow.active .dep2-flow {
  color: #b45309;
}

.dep2-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.dep2-line--main {
  justify-content: space-between;
  gap: 6px;
}

.dep2-flow-group {
  display: flex;
  align-items: baseline;
  gap: 4px;
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.dep2-flow {
  font-weight: 700;
  font-size: 12px;
  line-height: 1.3;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dep2-ver {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--muted);
}

.dep2-line--meta {
  gap: 6px;
  font-size: 11px;
}

.dep2-meta-cluster {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  flex: 1;
}

.dep2-id-sm {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  flex-shrink: 0;
}

.dep2-meta-rest {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dep2-time {
  flex-shrink: 0;
  font-size: 10px;
  max-width: 42%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}

.dep2-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dep2-main > .dep-create-panel {
  flex: 1;
  min-height: 0;
}

.dep2-main > .dep-sub-workspace {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.dep-detail-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
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
  font-family: inherit;
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s ease;
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

.dep-action-menu-wrap {
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
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  white-space: nowrap;
  box-shadow: var(--shadow);
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease;
}

.seg:hover:not(.active) {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 40%, var(--surface));
  color: var(--text);
}

.seg:focus {
  outline: none;
}

.seg:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  outline-offset: 2px;
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
  font-family: inherit;
  line-height: 1;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.icon-btn:focus {
  outline: none;
}

.icon-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  outline-offset: 1px;
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
