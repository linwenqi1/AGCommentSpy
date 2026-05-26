const Charts = {
  donut(container, data) {
    const labels = { Positive: '正面', Negative: '负面', Neutral: '中性' }
    const colors = { Positive: '#34d399', Negative: '#f87171', Neutral: '#60a5fa' }
    const entries = Object.entries(data).filter(([, v]) => v > 0)
    const total = entries.reduce((s, [, v]) => s + v, 0)
    if (!total) return

    const w = 240, h = 240, cx = w / 2, cy = h / 2, or = 100, ir = 60
    let svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`
    let start = -Math.PI / 2

    for (const [key, val] of entries) {
      const angle = (val / total) * 2 * Math.PI
      const end = start + angle
      const x1 = cx + or * Math.cos(start), y1 = cy + or * Math.sin(start)
      const x2 = cx + or * Math.cos(end), y2 = cy + or * Math.sin(end)
      const ix1 = cx + ir * Math.cos(start), iy1 = cy + ir * Math.sin(start)
      const ix2 = cx + ir * Math.cos(end), iy2 = cy + ir * Math.sin(end)
      const large = angle > Math.PI ? 1 : 0
      const d = `M ${ix1} ${iy1} L ${x1} ${y1} A ${or} ${or} 0 ${large} 1 ${x2} ${y2} L ${ix2} ${iy2} A ${ir} ${ir} 0 ${large} 0 ${ix1} ${iy1} Z`
      svg += `<path d="${d}" fill="${colors[key] || '#666'}" stroke="var(--bg-card)" stroke-width="2"/>`
      start = end
    }

    svg += `<text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central" fill="var(--text-primary)" font-size="1.4rem" font-family="var(--font-heading)">${total}</text>`
    svg += '</svg>'

    container.innerHTML = svg
    const lg = document.createElement('div')
    lg.className = 'legend'
    for (const [key, val] of entries) {
      const pct = ((val / total) * 100).toFixed(1)
      const item = document.createElement('div')
      item.className = 'legend-item'
      item.innerHTML = `<span class="legend-dot" style="background:${colors[key] || '#666'}"></span>${labels[key] || key} ${val} (${pct}%)`
      lg.appendChild(item)
    }
    container.appendChild(lg)
  },

  bar(container, data) {
    const entries = Object.entries(data)
    if (!entries.length) return
    const maxV = Math.max(...entries.map(([, v]) => v))
    const bh = 28, gap = 10, w = 500
    const h = Math.max(200, entries.length * (bh + gap))

    let svg = `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible">`
    for (const [i, [key, val]] of entries.entries()) {
      const y = i * (bh + gap)
      const bw = Math.max((val / maxV) * (w - 140), 4)
      const label = key.length > 6 ? key.slice(0, 6) + '..' : key
      svg += `<text x="0" y="${y + bh / 2 + 4}" fill="var(--text-secondary)" font-size="0.7rem">${label}</text>`
      svg += `<rect x="100" y="${y}" width="${bw}" height="${bh}" rx="4" fill="var(--accent)" opacity="0.85"><title>${key}: ${val}</title></rect>`
      svg += `<text x="${100 + bw + 6}" y="${y + bh / 2 + 4}" fill="var(--text-primary)" font-size="0.75rem">${val}</text>`
    }
    svg += '</svg>'
    container.innerHTML = svg
  },

  stars(rating) {
    const r = Math.round(parseFloat(rating))
    return '★'.repeat(r) + '☆'.repeat(5 - r)
  },
}
