/* Interactive sample workspace preview for the public Reachmark homepage. */
(function () {
  'use strict';
  var root = document.querySelector('[data-rm-preview]');
  if (!root) return;

  var examples = {
    clinic: {
      name: 'Willow Grove Dental',
      category: 'SAMPLE REPORT · HEALTHCARE',
      findings: [
        ['Make the next step obvious', 'Example: keep a clear appointment or call action easy to find on smaller screens.'],
        ['Answer key questions earlier', 'Example: help visitors quickly find services, opening hours, and what to expect.'],
        ['Reduce contact friction', 'Example: provide a simple, accessible route to ask a question or request an appointment.']
      ],
      next: 'Review the mobile appointment path and make the primary contact action easy to spot.'
    },
    law: {
      name: 'Northstar Family Law',
      category: 'SAMPLE REPORT · PROFESSIONAL SERVICES',
      findings: [
        ['Clarify the service path', 'Example: help visitors move from a practice area to a relevant next step without hunting.'],
        ['Write for the client’s first question', 'Example: explain who each service is for and what a first conversation involves.'],
        ['Make contact feel straightforward', 'Example: show a clear enquiry route and set expectations about the response process.']
      ],
      next: 'Map the journey from a service question to an enquiry and remove unnecessary steps.'
    },
    cafe: {
      name: 'Harborlight Café',
      category: 'SAMPLE REPORT · HOSPITALITY',
      findings: [
        ['Put local essentials within reach', 'Example: make hours, menu, location, and directions quick to find.'],
        ['Keep the visit decision simple', 'Example: surface the information people need before choosing to visit or order.'],
        ['Support mobile browsing', 'Example: make key details readable and easy to tap on a phone.']
      ],
      next: 'Prioritise a mobile-friendly path to the menu, current hours, and directions.'
    }
  };

  var name = document.getElementById('rm-preview-name');
  var category = document.getElementById('rm-preview-category');
  var list = document.getElementById('rm-preview-findings');
  var next = document.getElementById('rm-preview-next');
  var choices = Array.prototype.slice.call(root.querySelectorAll('[data-preview-select]'));

  function selectExample(key) {
    var item = examples[key];
    if (!item) return;
    choices.forEach(function (button) {
      var active = button.getAttribute('data-preview-select') === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    name.textContent = item.name;
    category.textContent = item.category;
    next.textContent = item.next;
    list.textContent = '';
    item.findings.forEach(function (finding, index) {
      var li = document.createElement('li');
      var number = document.createElement('span');
      number.className = 'rm-preview-finding-icon';
      number.textContent = String(index + 1).padStart(2, '0');
      var copy = document.createElement('div');
      var title = document.createElement('strong');
      title.textContent = finding[0];
      var detail = document.createElement('p');
      detail.textContent = finding[1];
      copy.appendChild(title);
      copy.appendChild(detail);
      li.appendChild(number);
      li.appendChild(copy);
      list.appendChild(li);
    });
  }

  choices.forEach(function (button) {
    button.addEventListener('click', function () {
      selectExample(button.getAttribute('data-preview-select'));
    });
  });
})();
