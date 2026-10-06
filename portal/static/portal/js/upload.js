// Sends essay files one at a time so large batches show progress and a
// single bad file cannot fail the whole upload.
(function () {
  var form = document.getElementById("upload-form");
  if (!form || !window.fetch) return;
  var input = document.getElementById("files");
  var zone = document.getElementById("dropzone");
  var list = document.getElementById("upload-list");
  var button = document.getElementById("upload-button");
  var progress = document.getElementById("upload-progress");
  var bar = progress.querySelector("span");
  var count = document.getElementById("upload-count");
  var dropped = null;

  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (event) { event.preventDefault(); zone.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (event) { event.preventDefault(); zone.classList.remove("over"); });
  });
  zone.addEventListener("drop", function (event) {
    dropped = Array.prototype.slice.call(event.dataTransfer.files);
    showPending(dropped);
  });
  input.addEventListener("change", function () {
    dropped = null;
    showPending(Array.prototype.slice.call(input.files));
  });

  function row(file) {
    var item = document.createElement("li");
    var name = document.createElement("span");
    name.className = "name"; name.textContent = file.name;
    var msg = document.createElement("span");
    msg.className = "msg"; msg.textContent = "…";
    item.appendChild(name); item.appendChild(msg);
    list.appendChild(item);
    return item;
  }
  function showPending(files) {
    list.innerHTML = "";
    files.forEach(row);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var files = dropped || Array.prototype.slice.call(input.files);
    if (!files.length) { input.click(); return; }
    list.innerHTML = "";
    var rows = files.map(row);
    button.disabled = true;
    progress.hidden = false;
    var token = form.querySelector("[name=csrfmiddlewaretoken]").value;
    var index = 0;

    function next() {
      count.textContent = form.dataset.progress + " " + Math.min(index + 1, files.length) + " / " + files.length;
      bar.style.width = Math.round(100 * index / files.length) + "%";
      if (index >= files.length) {
        count.textContent = form.dataset.done;
        button.disabled = false;
        input.value = ""; dropped = null;
        document.getElementById("review-link").hidden = false;
        return;
      }
      var data = new FormData();
      data.append("csrfmiddlewaretoken", token);
      data.append("division", form.querySelector("[name=division]").value);
      data.append("prompt", form.querySelector("[name=prompt]").value);
      data.append("file", files[index]);
      var item = rows[index];
      fetch(form.dataset.url, { method: "POST", body: data, credentials: "same-origin" })
        .then(function (response) { return response.json(); })
        .then(function (result) {
          item.className = result.outcome;
          item.querySelector(".msg").textContent = result.message;
        })
        .catch(function () {
          item.className = "error";
          item.querySelector(".msg").textContent = form.dataset.failed;
        })
        .then(function () { index += 1; next(); });
    }
    next();
  });
})();
