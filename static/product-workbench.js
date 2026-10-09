/* Product-first homepage enhancements: explicit example switching and evidence-ranked next steps. */
(function () {
  'use strict';

  var report = document.querySelector('.x-report');
  if (report && !report.querySelector('[data-ph-example-switcher]')) {
    var intro = report.querySelector('.x-report-disc');
    var sheet = report.querySelector('.x-report-sheet');
    if (intro && sheet) {
      var examples = [
        {
          key: 'response',
          tab: 'Page response',
          title: 'Start with what the server returned',
          observed: 'A report can record the HTTP status and response time when the public page fetch succeeds.',
          why: 'This describes the response observed during the check; it does not predict traffic, enquiries, or revenue.',
          next: 'Review the recorded status and response time, then decide whether a deeper check is needed.'
        },
        {
          key: 'identity',
          tab: 'Page identity',
          title: 'Show the page identity that was actually read',
          observed: 'When a page title is available, the report can quote the title read from the fetched page.',
          why: 'The title is a concrete page signal. It is not, by itself, proof that a business is losing customers.',
          next: 'Compare the observed title with the page purpose and the business name before recommending a change.'
        },
        {
          key: 'gaps',
          tab: 'Website gaps',
          title: 'Connect each opportunity to its evidence',
          observed: 'When a labelled gap check fires, the report shows the finding and the evidence returned by the page read.',
          why: 'A finding is useful only when the reader can see what triggered it and what remains unknown.',
          next: 'Open the full Digital Opportunity Report to review the evidence and choose a practical fix.'
        }
      ];
      var wrap = document.createElement('div');
      wrap.className = 'ph-example-switcher';
      wrap.setAttribute('data-ph-example-switcher', '');
      wrap.innerHTML = '<div class="ph-example-top"><div><span class="ph-example-kicker">REPORT EXPLORER</span><h3>Switch the evidence pattern</h3></div><span class="ph-example-disclaimer">Illustrative examples · not client results</span></div><div class="ph-example-tabs" role="tablist" aria-label="Switch report examples"></div><article class="ph-example-panel" role="tabpanel" aria-live="polite"></article>';
      var tabs = wrap.querySelector('.ph-example-tabs');
      var panel = wrap.querySelector('.ph-example-panel');

      function showExample(index, focusTab) {
        var item = examples[index];
        Array.prototype.forEach.call(tabs.querySelectorAll('button'), function (button, i) {
          button.setAttribute('aria-selected', i === index ? 'true' : 'false');
          button.tabIndex = i === index ? 0 : -1;
        });
        panel.textContent = '';
        var heading = document.createElement('h4');
        heading.textContent = item.title;
        panel.appendChild(heading);
        [
          ['Observed signal', item.observed],
          ['How to interpret it', item.why],
          ['Recommended next step', item.next]
        ].forEach(function (pair) {
          var block = document.createElement('div');
          block.className = 'ph-example-row';
          var label = document.createElement('strong');
          label.textContent = pair[0];
          var copy = document.createElement('p');
          copy.textContent = pair[1];
          block.appendChild(label);
          block.appendChild(copy);
          panel.appendChild(block);
        });
        if (focusTab) tabs.querySelectorAll('button')[index].focus();
      }

      examples.forEach(function (item, index) {
        var button = document.createElement('button');
        button.type = 'button';
        button.role = 'tab';
        button.textContent = item.tab;
        button.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
        button.tabIndex = index === 0 ? 0 : -1;
        button.addEventListener('click', function () { showExample(index, false); });
        button.addEventListener('keydown', function (event) {
          if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft' && event.key !== 'Home' && event.key !== 'End') return;
          event.preventDefault();
          var next = index;
          if (event.key === 'ArrowRight') next = (index + 1) % examples.length;
          if (event.key === 'ArrowLeft') next = (index + examples.length - 1) % examples.length;
          if (event.key === 'Home') next = 0;
          if (event.key === 'End') next = examples.length - 1;
          showExample(next, true);
        });
        tabs.appendChild(button);
      });
      intro.insertAdjacentElement('afterend', wrap);
      showExample(0, false);
    }
  }

  var output = document.getElementById('x-audit-out');
  if (!output || !window.MutationObserver) return;
  function renderRankedOpportunities() {
    var old = output.querySelector('.ph-ranked-opportunities');
    var list = output.querySelector('.x-audit-leaks');
    if (old && list && old.dataset.sourceList === list.innerHTML) return;
    if (old) old.remove();
    if (!list || !list.children.length) return;
    var rows = Array.prototype.slice.call(list.querySelectorAll('li')).slice(0, 3);
    if (!rows.length) return;

    var section = document.createElement('section');
    section.className = 'ph-ranked-opportunities';
    section.dataset.sourceList = list.innerHTML;
    var heading = document.createElement('div');
    heading.className = 'ph-ranked-head';
    var title = document.createElement('h3');
    title.textContent = 'Ranked opportunities';
    var note = document.createElement('p');
    note.textContent = 'Ordered by the audit service’s measured gap weights. No invented score or revenue estimate.';
    heading.appendChild(title);
    heading.appendChild(note);
    section.appendChild(heading);

    var cards = document.createElement('div');
    cards.className = 'ph-ranked-grid';
    rows.forEach(function (row, index) {
      var card = document.createElement('article');
      card.className = 'ph-ranked-card';
      var rank = document.createElement('span');
      rank.className = 'ph-ranked-number';
      rank.textContent = 'PRIORITY ' + (index + 1);
      var sourceTitle = row.querySelector('strong');
      var sourceCopy = row.querySelectorAll('span');
      var cardTitle = document.createElement('h4');
      cardTitle.textContent = sourceTitle ? sourceTitle.textContent : 'Measured observation';
      var evidence = document.createElement('p');
      evidence.textContent = sourceCopy.length ? sourceCopy[0].textContent : row.textContent;
      var next = document.createElement('p');
      next.className = 'ph-ranked-next';
      next.textContent = 'Next step: review this evidence in the full report before deciding on a fix.';
      card.appendChild(rank);
      card.appendChild(cardTitle);
      card.appendChild(evidence);
      card.appendChild(next);
      cards.appendChild(card);
    });
    section.appendChild(cards);
    list.insertAdjacentElement('afterend', section);
  }
  var observer = new MutationObserver(renderRankedOpportunities);
  observer.observe(output, { childList: true, subtree: true });
  renderRankedOpportunities();
})();
