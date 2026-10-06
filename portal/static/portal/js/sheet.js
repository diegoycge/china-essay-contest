// Judging sheet: live totals and word counts, rubric band highlight, autosave.
(function () {
  var form = document.getElementById("sheet-form");
  if (!form) return;

  var countWords = function (text) {
    if (!text) return 0;
    var cjk = /[㐀-䶿一-鿿豈-﫿]/g;
    var han = text.match(cjk) || [];
    var words = text.replace(cjk, " ").match(/[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*/g) || [];
    return han.length + words.length;
  };

  var locked = form.dataset.locked === "1";
  var minWords = parseInt(form.dataset.minWords, 10) || 0;
  var bounds = JSON.parse(document.getElementById("level-bounds").textContent);
  var criteria = Array.prototype.slice.call(form.querySelectorAll("[data-criterion]"));
  var selects = criteria.map(function (c) { return c.querySelector("select"); });
  var counted = Array.prototype.slice.call(form.querySelectorAll(".criterion textarea")).filter(function (t) {
    return t.name !== "flag_notes";
  });
  var status = document.getElementById("save-status");

  function refresh() {
    var total = 0, scored = 0;
    criteria.forEach(function (card, i) {
      var value = selects[i].value;
      var levels = card.querySelectorAll(".level");
      var band = -1;
      if (value !== "") {
        var n = parseFloat(value);
        total += n; scored += 1;
        for (band = 0; band < bounds.length - 1 && n > bounds[band]; band++) {}
      }
      levels.forEach(function (level, index) { level.classList.toggle("current", index === band); });
    });
    document.getElementById("sum-total").textContent = scored ? total.toFixed(1) : "—";
    document.getElementById("sum-average").textContent = scored === 4 ? (total / 4).toFixed(2) : "—";

    var words = 0;
    counted.forEach(function (area) {
      var n = countWords(area.value);
      words += n;
      var label = area.parentNode.querySelector("[data-words]");
      if (label) label.textContent = n;
    });
    var box = document.getElementById("sum-words-box");
    document.getElementById("sum-words").textContent = words;
    box.classList.toggle("met", words >= minWords);
    box.classList.toggle("short", words < minWords);
  }
  refresh();

  // Page zoom (remembered per browser) and the pages / text switch.
  var pagesView = document.getElementById("essay-pages");
  var textView = document.getElementById("essay-text");
  var zoom = parseInt(localStorage.getItem("essayZoom"), 10) || 100;
  function applyZoom() {
    pagesView.style.width = zoom + "%";
    pagesView.style.maxWidth = zoom > 100 ? "none" : "";
  }
  applyZoom();
  document.querySelectorAll("[data-zoom]").forEach(function (button) {
    button.addEventListener("click", function () {
      zoom = Math.max(50, Math.min(220, zoom + 15 * parseInt(button.dataset.zoom, 10)));
      localStorage.setItem("essayZoom", zoom);
      applyZoom();
    });
  });
  document.querySelectorAll("[data-view]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll("[data-view]").forEach(function (other) {
        other.classList.toggle("active", other === tab);
      });
      pagesView.hidden = tab.dataset.view !== "pages";
      textView.hidden = tab.dataset.view !== "text";
    });
  });

  if (locked) return;

  var dirty = false, saving = false, timer = null, submitting = false;

  function save() {
    if (!dirty || saving) return;
    saving = true; dirty = false;
    status.textContent = form.dataset.msgSaving;
    fetch(form.dataset.autosaveUrl, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).then(function (response) {
      if (!response.ok) throw new Error(response.status);
      return response.json();
    }).then(function (data) {
      saving = false;
      status.textContent = form.dataset.msgSaved + " " + data.saved_at;
      if (dirty) schedule();
    }).catch(function () {
      saving = false; dirty = true;
      status.textContent = form.dataset.msgError;
    });
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(save, 2500);
  }
  function changed() {
    dirty = true;
    status.textContent = form.dataset.msgUnsaved;
    refresh();
    schedule();
  }
  form.addEventListener("input", changed);
  form.addEventListener("change", changed);

  form.addEventListener("submit", function (event) {
    var button = event.submitter;
    if (button && button.value === "submit" && !window.confirm(form.dataset.msgConfirm)) {
      event.preventDefault();
      return;
    }
    submitting = true;
    clearTimeout(timer);
  });
  window.addEventListener("beforeunload", function (event) {
    if (dirty && !submitting) { event.preventDefault(); event.returnValue = ""; }
  });
})();
