/* Interactive sample workspace preview for the public Reachmark homepage. */
(function () {
  'use strict';
  var root = document.querySelector('[data-rm-preview]');
  if (!root) return;

  var examples = {
    clinic: {
      name: 'Willow Grove Dental',
      category: 'SAMPLE WEBSITE REVIEW · HEALTHCARE',
      findings: [
        ['Make the next step obvious', 'Make the appointment or phone option easy to find, especially on a mobile screen.'],
        ['Answer key questions earlier', 'Help visitors find the services, opening hours, and information they need before booking.'],
        ['Reduce contact friction', 'Give visitors a clear way to ask a question or request an appointment.']
      ],
      next: 'Make the appointment and contact options easy to find on a phone.'
    },
    law: {
      name: 'Northstar Family Law',
      category: 'SAMPLE WEBSITE REVIEW · PROFESSIONAL SERVICES',
      findings: [
        ['Clarify the service path', 'Help visitors move from a service description to a relevant next step.'],
        ['Write for the client’s first question', 'Explain who each service is for and what a first conversation involves.'],
        ['Make contact feel straightforward', 'Make it easy to enquire and explain what happens after someone gets in touch.']
      ],
      next: 'Make it straightforward for a visitor to understand a service and send an enquiry.'
    },
    cafe: {
      name: 'Harborlight Café',
      category: 'SAMPLE WEBSITE REVIEW · HOSPITALITY',
      findings: [
        ['Put local essentials within reach', 'Make the opening hours, menu, location, and directions easy to find.'],
        ['Keep the visit decision simple', 'Help visitors find the details they need before deciding to visit or order.'],
        ['Support mobile browsing', 'Make important information easy to read and use on a phone.']
      ],
      next: 'Make the menu, opening hours, and directions easy to find on a phone.'
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
