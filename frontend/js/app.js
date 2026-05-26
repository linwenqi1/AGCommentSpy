const App = {
  state: { apps: [], currentApp: null, currentTab: 'overview', commentsPage: 1, commentsSearch: '', analysisDim: null, clusterDim: null },

  init() {
    this.loadApps()
    this.setupTabs()
  },

  async loadApps() {
    const el = document.getElementById('app-list')
    el.innerHTML = '<div class="loading">加载中...</div>'
    try {
      const apps = await API.getApps()
      this.state.apps = apps
      this.renderAppList(apps)
      if (apps.length) this.selectApp(apps[0].package)
    } catch (e) {
      el.innerHTML = `<div class="empty-state">加载失败: ${e.message}</div>`
    }
  },

  renderAppList(apps) {
    const el = document.getElementById('app-list')
    el.innerHTML = apps.map(a =>
      `<div class="app-item${this.state.currentApp === a.package ? ' active' : ''}" data-pkg="${a.package}">
        <span class="dot"></span>${a.title}
      </div>`
    ).join('')
    el.querySelectorAll('.app-item').forEach(el =>
      el.addEventListener('click', () => this.selectApp(el.dataset.pkg)))
  },

  async selectApp(pkg) {
    this.state.currentApp = pkg
    this.state.commentsPage = 1
    this.state.commentsSearch = ''
    this.renderAppList(this.state.apps)
    const app = this.state.apps.find(a => a.package === pkg)
    document.getElementById('app-title').innerHTML =
      `<h2>${app.title}</h2>${app.subtitle ? `<span class="subtitle-text">${app.subtitle}</span>` : ''}`
    this.loadTab(this.state.currentTab)
  },

  setupTabs() {
    document.querySelectorAll('.tab').forEach(t => {
      t.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'))
        t.classList.add('active')
        this.state.currentTab = t.dataset.tab
        this.loadTab(t.dataset.tab)
      })
    })
  },

  async loadTab(tab) {
    if (!this.state.currentApp) return
    const ct = document.getElementById('content')
    ct.innerHTML = '<div class="loading">加载中...</div>'
    try {
      const fns = { overview: 'renderOverview', comments: 'renderComments', analysis: 'renderAnalysis', clusters: 'renderClusters' }
      await this[fns[tab]](ct)
    } catch (e) {
      ct.innerHTML = `<div class="empty-state">加载失败: ${e.message}</div>`
    }
  },

  async renderOverview(ct) {
    const info = await API.getAppInfo(this.state.currentApp)
    const s = info.stats
    ct.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-label">评论总数</div><div class="stat-value">${s.total_comments.toLocaleString()}</div></div>
        <div class="stat-card"><div class="stat-label">已分类</div><div class="stat-value">${s.total_classified.toLocaleString()}</div></div>
        <div class="stat-card"><div class="stat-label">正面</div><div class="stat-value positive">${s.sentiment_distribution.Positive.toLocaleString()}</div></div>
        <div class="stat-card"><div class="stat-label">负面</div><div class="stat-value negative">${s.sentiment_distribution.Negative.toLocaleString()}</div></div>
      </div>
      <div class="charts-grid">
        <div class="chart-card"><h3>情感分布</h3><div id="chart-sentiment" class="chart-container"></div></div>
        <div class="chart-card"><h3>各维度分析量</h3><div id="chart-dimension" class="chart-container"></div></div>
      </div>`
    Charts.donut(document.getElementById('chart-sentiment'), s.sentiment_distribution)
    Charts.bar(document.getElementById('chart-dimension'), s.dimension_distribution)
  },

  async renderComments(ct) {
    const pkg = this.state.currentApp
    const data = await API.getComments(pkg, this.state.commentsPage, 50, this.state.commentsSearch)
    ct.innerHTML = `
      <div class="comments-controls">
        <input type="text" class="search-input" placeholder="搜索评论内容..." id="search-input" value="${this.esc(this.state.commentsSearch)}">
      </div>
      <div class="comments-count">共 ${data.total} 条评论</div>
      <div id="comments-list">
        ${data.comments.map(c => `
          <div class="comment-item">
            <div class="comment-header">
              <div class="comment-user">
                <span class="comment-username">${this.esc(c.username)}</span>
                <span class="comment-rating">${Charts.stars(c.rating)}</span>
              </div>
              <div class="comment-meta">
                <span>${c.date}</span>
                <span>${this.esc(c.location)}</span>
              </div>
            </div>
            <div class="comment-content">${this.esc(c.content)}</div>
            <div class="comment-footer">
              <span class="comment-device">${this.esc(c.device)}</span>
            </div>
          </div>`).join('')}
        ${data.comments.length === 0 ? '<div class="empty-state">没有匹配的评论</div>' : ''}
      </div>
      ${data.total_pages > 1 ? `
        <div class="pagination">
          <button ${data.page <= 1 ? 'disabled' : ''} onclick="App.goPage(${data.page - 1})">上一页</button>
          <span class="page-info">${data.page} / ${data.total_pages}</span>
          <button ${data.page >= data.total_pages ? 'disabled' : ''} onclick="App.goPage(${data.page + 1})">下一页</button>
        </div>` : ''}`
    document.getElementById('search-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        this.state.commentsSearch = e.target.value
        this.state.commentsPage = 1
        this.loadTab('comments')
      }
    })
  },

  goPage(p) {
    this.state.commentsPage = p
    this.loadTab('comments')
  },

  async renderAnalysis(ct) {
    const data = await API.getAnalysis(this.state.currentApp)
    const dims = Object.keys(data)
    if (!this.state.analysisDim || !dims.includes(this.state.analysisDim))
      this.state.analysisDim = dims[0]
    const active = this.state.analysisDim
    ct.innerHTML = `
      <div class="dim-tabs">${dims.map(d =>
        `<button class="dim-tab${d === active ? ' active' : ''}" data-dim="${d}">${d}</button>`
      ).join('')}</div>
      <div id="analysis-content"></div>`
    ct.querySelectorAll('.dim-tab').forEach(t => {
      t.addEventListener('click', () => {
        this.state.analysisDim = t.dataset.dim
        this.loadTab('analysis')
      })
    })
    const ac = document.getElementById('analysis-content')
    const sents = ['Negative', 'Positive', 'Neutral']
    const sl = { Negative: '负面', Positive: '正面', Neutral: '中性' }
    const sc = { Negative: 'negative', Positive: 'positive', Neutral: 'neutral' }
    ac.innerHTML = sents.map(s => {
      const items = data[active]?.[s]
      if (!items?.length) return ''
      return `
        <div class="sentiment-group">
          <div class="sentiment-header">
            <span class="sentiment-badge ${sc[s]}">${sl[s]}</span>
            <span class="sentiment-count">${items.length} 条</span>
          </div>
          ${items.map((item, i) => `
            <div class="analysis-item">
              <div class="analysis-main">
                <div class="pain"><span class="label">痛点</span>${this.esc(item.User_Pain_Point)}</div>
                <div class="suggestion"><span class="label">建议</span>${this.esc(item.Actionable_Suggestion)}</div>
              </div>
              ${item.original ? `
                <div class="original-comment">
                  <div class="original-header">
                    <span class="original-user">${this.esc(item.original.username)}</span>
                    <span>${Charts.stars(item.original.rating)}</span>
                    <span class="original-meta">${item.original.date} · ${this.esc(item.original.location)} · ${this.esc(item.original.device)}</span>
                  </div>
                  <div class="original-text">${this.esc(item.original.content)}</div>
                </div>` : ''}
            </div>`).join('')}
        </div>`
    }).join('')
  },

  async renderClusters(ct) {
    const data = await API.getClusters(this.state.currentApp)
    const dims = {}
    for (const [k, v] of Object.entries(data))
      if (!k.startsWith('n_')) dims[k] = v
    if (!this.state.clusterDim || !dims[this.state.clusterDim])
      this.state.clusterDim = Object.keys(dims)[0]
    const active = this.state.clusterDim
    ct.innerHTML = `
      <div class="dim-tabs">${Object.keys(dims).map(d =>
        `<button class="dim-tab${d === active ? ' active' : ''}" data-dim="${d}">${d}</button>`
      ).join('')}</div>
      <div class="cluster-summary">共 ${data.n_clusters || 0} 个聚类 · ${data.n_items || 0} 条评论</div>
      <div id="cluster-content"></div>`
    ct.querySelectorAll('.dim-tab').forEach(t => {
      t.addEventListener('click', () => {
        this.state.clusterDim = t.dataset.dim
        this.loadTab('clusters')
      })
    })
    const cc = document.getElementById('cluster-content')
    const sentiments = dims[active] || {}
    const sl = { negative: '负面', positive: '正面', neutral: '中性' }
    const sc = { negative: 'negative', positive: 'positive', neutral: 'neutral' }
    cc.innerHTML = Object.entries(sentiments).map(([s, sd]) => {
      if (!sd.clusters?.length) return ''
      return `
        <div class="sentiment-group">
          <div class="sentiment-header">
            <span class="sentiment-badge ${sc[s]}">${sl[s] || s}</span>
            <span class="sentiment-count">${sd.clusters.length} 个聚类</span>
          </div>
          ${sd.clusters.map(c => {
            const cid = `${active}-${s}-${c.cluster_id}`
            const n = c.sample_members?.length || 0
            return `
            <div class="cluster-card">
              <div class="cluster-header">
                <span class="cluster-name">${this.esc(c.cluster_name)}</span>
                <span class="cluster-size">${c.size} 条</span>
              </div>
              <div class="cluster-issue">${this.esc(c.canonical_issue)}</div>
              <button class="cluster-toggle" data-cmid="${cid}" data-n="${n}">查看样本 (${n})</button>
              <div class="cluster-members" id="cm-${cid}">
                ${(c.sample_members || []).map(m => `
                  <div class="sample-item">
                    <div class="sample-pain">${this.esc(m.pain)}</div>
                    <div class="sample-suggestion">${this.esc(m.suggestion)}</div>
                    ${m.device ? `<div class="sample-device">${this.esc(m.device)}</div>` : ''}
                  </div>`).join('')}
              </div>
            </div>`}).join('')}
        </div>`
    }).join('')
    cc.querySelectorAll('.cluster-toggle').forEach(b => {
      b.addEventListener('click', () => {
        const m = document.getElementById(`cm-${b.dataset.cmid}`)
        m.classList.toggle('open')
        const n = b.dataset.n
        b.textContent = m.classList.contains('open')
          ? `收起样本` : `查看样本 (${n})`
      })
    })
  },

  esc(s) {
    if (!s) return ''
    const d = document.createElement('div')
    d.textContent = s
    return d.innerHTML
  },
}

document.addEventListener('DOMContentLoaded', () => App.init())
