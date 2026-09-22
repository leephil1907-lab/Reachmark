/* Activity heatmap (contribution-graph style): one square per day, drawn from the
   same /api/analytics timeline the line chart uses. Empty days stay empty. */
(function () {
  'use strict';
  function level(value, max) {
    if (!value || !max) return 0;
    var ratio = value / max;
    return ratio > 0.75 ? 4 : ratio > 0.5 ? 3 : ratio > 0.25 ? 2 : 1;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function renderHeatmap() {
    var box = document.getElementById('activity-heatmap');
    if (!box || !window.analyticsData) return;
    var seriesEl = document.getElementById('chart-series');
    var series = seriesEl ? seriesEl.value : 'leads';
    var label = seriesEl && seriesEl.selectedOptions ? seriesEl.selectedOptions[0].text : series;
    var rows = window.analyticsData.timeline || [];
    if (!rows.length) {
      box.innerHTML = '<p class="small muted">No days recorded yet.</p>';
      return;
    }
    var values = rows.map(function (row) { return row[series] || 0; });
    var max = Math.max.apply(null, values.concat([1]));
    var cells = rows.map(function (row, i) {
      return '<span class="hm-cell hm-' + level(values[i], max) + '" title="' +
        esc(row.date) + ': ' + values[i] + '"></span>';
    }).join('');
    box.innerHTML = '<div class="hm-grid" role="img" aria-label="' + esc(label) +
      ' per day, last ' + rows.length + ' days">' + cells + '</div>' +
      '<div class="hm-legend"><span>Less</span>' +
      '<span class="hm-cell hm-0"></span><span class="hm-cell hm-1"></span>' +
      '<span class="hm-cell hm-2"></span><span class="hm-cell hm-3"></span>' +
      '<span class="hm-cell hm-4"></span><span>More</span></div>';
  }
  window.renderHeatmap = renderHeatmap;
})();
