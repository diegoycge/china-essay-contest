// Site-wide: confirmation prompts declared with data-confirm on a form or button.
(function () {
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var source = event.submitter && event.submitter.dataset.confirm ? event.submitter : form;
    var message = source.dataset ? source.dataset.confirm : null;
    if (message && !window.confirm(message)) event.preventDefault();
  });
})();
(function () {
  document.addEventListener("click", function (event) {
    var link = event.target.closest ? event.target.closest("a[data-confirm-link]") : null;
    if (link && !window.confirm(link.dataset.confirmLink)) event.preventDefault();
  });
})();
(function () {
  // One-time links: select on focus, copy on click. (No inline handlers, so a
  // strict Content-Security-Policy can stay on.)
  document.addEventListener("focusin", function (event) {
    if (event.target.matches && event.target.matches("[data-select-on-focus]")) event.target.select();
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-copy]") : null;
    if (!button) return;
    var field = document.getElementById(button.dataset.copy);
    function done() { button.textContent = "✓"; }
    function fallback() {
      field.focus(); field.select();
      if (document.execCommand("copy")) done();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(field.value).then(done, fallback);
    } else {
      fallback();
    }
  });
})();
