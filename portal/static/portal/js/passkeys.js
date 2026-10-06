// Passkeys: creating one and signing in with one.
//
// A button with data-passkey="register" or "login" starts the ceremony. The
// server issues a challenge, the browser asks the device (fingerprint, face
// or PIN), and the signed answer goes back to the server.
(function () {
  var blocks = document.querySelectorAll("[data-passkey-ui]");
  if (!blocks.length) return;
  if (!window.PublicKeyCredential || !navigator.credentials) {
    // This browser cannot do passkeys; the password form remains.
    blocks.forEach(function (block) { block.hidden = true; });
    document.querySelectorAll("[data-passkey-missing]").forEach(function (note) { note.hidden = false; });
    return;
  }

  function toBuffer(text) {
    var base64 = text.replace(/-/g, "+").replace(/_/g, "/");
    while (base64.length % 4) base64 += "=";
    var binary = atob(base64), bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }
  function toText(buffer) {
    var bytes = new Uint8Array(buffer), binary = "";
    for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function describe(credential) {
    var response = credential.response;
    var out = {
      id: credential.id,
      rawId: toText(credential.rawId),
      type: credential.type,
      clientExtensionResults: credential.getClientExtensionResults ? credential.getClientExtensionResults() : {},
      response: { clientDataJSON: toText(response.clientDataJSON) }
    };
    if (credential.authenticatorAttachment) out.authenticatorAttachment = credential.authenticatorAttachment;
    if (response.attestationObject) {
      out.response.attestationObject = toText(response.attestationObject);
      if (response.getTransports) out.response.transports = response.getTransports();
    } else {
      out.response.authenticatorData = toText(response.authenticatorData);
      out.response.signature = toText(response.signature);
      if (response.userHandle && response.userHandle.byteLength) out.response.userHandle = toText(response.userHandle);
    }
    return out;
  }
  function post(url, data) {
    var token = document.querySelector("[name=csrfmiddlewaretoken]").value;
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(data)
    }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) { var error = new Error(body.error || "failed"); error.code = body.error; throw error; }
        return body;
      });
    });
  }

  blocks.forEach(function (block) {
    var button = block.querySelector("[data-passkey]");
    var status = block.querySelector("[data-passkey-status]");
    if (!button) return;
    var registering = button.dataset.passkey === "register";
    var extra = {};
    if (button.dataset.token) { extra.token = button.dataset.token; extra.purpose = button.dataset.purpose; }
    if (button.dataset.next) extra.next = button.dataset.next;

    button.addEventListener("click", function () {
      button.disabled = true;
      status.textContent = block.dataset.msgWaiting;
      status.className = "small muted";
      post(button.dataset.optionsUrl, extra).then(function (options) {
        options.challenge = toBuffer(options.challenge);
        if (registering) {
          options.user.id = toBuffer(options.user.id);
          (options.excludeCredentials || []).forEach(function (item) { item.id = toBuffer(item.id); });
          return navigator.credentials.create({ publicKey: options });
        }
        (options.allowCredentials || []).forEach(function (item) { item.id = toBuffer(item.id); });
        return navigator.credentials.get({ publicKey: options });
      }).then(function (credential) {
        var payload = { credential: describe(credential) };
        Object.keys(extra).forEach(function (key) { payload[key] = extra[key]; });
        return post(button.dataset.verifyUrl, payload);
      }).then(function (result) {
        window.location.assign(result.redirect);
      }).catch(function (error) {
        button.disabled = false;
        status.className = "small error";
        if (error && (error.name === "NotAllowedError" || error.name === "AbortError")) {
          status.textContent = block.dataset.msgCancelled;   // dismissed, or timed out
        } else if (error && error.name === "InvalidStateError") {
          status.textContent = block.dataset.msgExists;      // this device already has one
        } else if (error && error.code === "unknown") {
          status.textContent = block.dataset.msgUnknown;     // passkey not registered here
        } else if (error && error.code === "throttled") {
          status.textContent = block.dataset.msgThrottled;
        } else {
          status.textContent = block.dataset.msgFailed;
        }
      });
    });
  });
})();
