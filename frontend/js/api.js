const API = {
  async fetch(url) {
    const res = await fetch(url)
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }))
      throw new Error(err.error || '请求失败')
    }
    return res.json()
  },
  getApps() { return this.fetch('/api/apps') },
  getAppInfo(pkg) { return this.fetch(`/api/apps/${pkg}`) },
  getComments(pkg, page = 1, limit = 50, search = '') {
    let url = `/api/apps/${pkg}/comments?page=${page}&limit=${limit}`
    if (search) url += `&search=${encodeURIComponent(search)}`
    return this.fetch(url)
  },
  getAnalysis(pkg) { return this.fetch(`/api/apps/${pkg}/analysis`) },
  getClusters(pkg) { return this.fetch(`/api/apps/${pkg}/clusters`) },
}
