document.addEventListener('DOMContentLoaded', function () {
  var toggle = document.querySelector('.nav-toggle');
  var mobileNav = document.querySelector('.mobile-nav');
  if (toggle && mobileNav) {
    toggle.addEventListener('click', function () {
      var isOpen = mobileNav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(isOpen));
    });
  }

  var contactForm = document.getElementById('contact-form');
  if (contactForm) {
    contactForm.addEventListener('submit', function (event) {
      event.preventDefault();
      var get = function (name) {
        var field = contactForm.elements.namedItem(name);
        return field ? field.value.trim() : '';
      };
      var subject = 'Frontdesk enquiry from ' + (get('name') || 'website visitor');
      var bodyLines = [
        'Name: ' + get('name'),
        'Business: ' + get('business'),
        'Phone: ' + get('phone'),
        'Business type: ' + get('type'),
        '',
        get('message')
      ];
      var mailto = 'mailto:hello@rivance.co.za'
        + '?subject=' + encodeURIComponent(subject)
        + '&body=' + encodeURIComponent(bodyLines.join('\n'));
      window.location.href = mailto;
    });
  }
});
