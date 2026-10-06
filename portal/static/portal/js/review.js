// Anonymization review: redaction boxes on page images.
//
// State is a list of boxes {p, x, y, w, h, kind, on} in fractions of the page,
// plus a list of pages left out. Nothing is sent until the form is submitted.
(function () {
  var form = document.getElementById("review-form");
  var source = document.getElementById("review-state");
  if (!form || !source) return;
  var state = JSON.parse(source.textContent);
  var boxes = state.redactions || [];
  var dropped = state.dropped || [];
  var hand = { manual: true, term: true };
  var dirty = false;
  var sections = Array.prototype.slice.call(document.querySelectorAll(".rpage"));

  function touch() { dirty = true; counts(); }

  function counts() {
    var on = 0, off = 0;
    boxes.forEach(function (box) {
      if (dropped.indexOf(box.p) !== -1) return;
      if (box.on) on += 1; else off += 1;
    });
    document.getElementById("count-on").textContent = on;
    document.getElementById("count-off").textContent = off;
  }

  function place(element, box) {
    element.style.left = box.x * 100 + "%";
    element.style.top = box.y * 100 + "%";
    element.style.width = box.w * 100 + "%";
    element.style.height = box.h * 100 + "%";
  }

  function draw(section) {
    var page = parseInt(section.dataset.page, 10);
    var layer = section.querySelector(".rpage-layer");
    layer.textContent = "";
    boxes.forEach(function (box) {
      if (box.p !== page) return;
      var element = document.createElement("div");
      element.className = "rbox " + (box.on ? "on" : "off") + (hand[box.kind] ? " hand" : "");
      if (box.t) element.title = box.t;
      place(element, box);
      element.addEventListener("pointerdown", function (event) { event.stopPropagation(); });
      element.addEventListener("click", function (event) {
        event.stopPropagation();
        if (hand[box.kind]) boxes.splice(boxes.indexOf(box), 1);  // your own box: remove it
        else box.on = !box.on;                                     // a found one: on or off
        draw(section); touch();
      });
      layer.appendChild(element);
    });
    var isOut = dropped.indexOf(page) !== -1;
    section.classList.toggle("dropped", isOut);
    var button = section.querySelector("[data-drop]");
    button.textContent = isOut ? button.dataset.labelKeep : button.dataset.labelDrop;
  }

  sections.forEach(function (section) {
    var page = parseInt(section.dataset.page, 10);
    var layer = section.querySelector(".rpage-layer");
    var band = null, origin = null;

    function point(event) {
      var rect = layer.getBoundingClientRect();
      return {
        x: Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1),
        y: Math.min(Math.max((event.clientY - rect.top) / rect.height, 0), 1)
      };
    }
    function shape(a, b) {
      return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) };
    }

    layer.addEventListener("pointerdown", function (event) {
      if (event.button !== 0 || section.classList.contains("dropped")) return;
      origin = point(event);
      band = document.createElement("div");
      band.className = "rbox band";
      layer.appendChild(band);
      layer.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    layer.addEventListener("pointermove", function (event) {
      if (band) place(band, shape(origin, point(event)));
    });
    function finish(event) {
      if (!band) return;
      var rect = shape(origin, point(event));
      band = null; origin = null;
      if (rect.w > 0.004 && rect.h > 0.004) {
        boxes.push({
          p: page, kind: "manual", on: true,
          x: +rect.x.toFixed(4), y: +rect.y.toFixed(4), w: +rect.w.toFixed(4), h: +rect.h.toFixed(4)
        });
        touch();
      }
      draw(section);
    }
    layer.addEventListener("pointerup", finish);
    layer.addEventListener("pointercancel", function () { band = null; origin = null; draw(section); });

    section.querySelector("[data-drop]").addEventListener("click", function () {
      var at = dropped.indexOf(page);
      if (at === -1) dropped.push(page); else dropped.splice(at, 1);
      draw(section); touch();
    });
    draw(section);
  });
  counts();

  document.querySelectorAll("[data-view]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll("[data-view]").forEach(function (other) {
        other.classList.toggle("active", other === tab);
      });
      document.getElementById("view-pages").hidden = tab.dataset.view !== "pages";
      document.getElementById("view-text").hidden = tab.dataset.view !== "text";
    });
  });

  form.addEventListener("submit", function () {
    document.getElementById("state").value = JSON.stringify({ redactions: boxes, dropped: dropped });
    dirty = false;
  });
  window.addEventListener("beforeunload", function (event) {
    if (dirty) { event.preventDefault(); event.returnValue = form.dataset.leave; }
  });
})();
