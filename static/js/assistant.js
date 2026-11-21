/* GachGhar AI Gardener chat widget. Vanilla JavaScript, no dependencies.
   Rules: text is always inserted with textContent (never innerHTML); success messages for cart, wishlist and
   cancellation are shown ONLY from the backend's "actions" list; cards show backend data (prices, stock, totals). */
(function () {
  "use strict";

  var root = document.querySelector("[data-gardener]");
  if (!root) return;

  var inline = root.hasAttribute("data-inline");
  var panel = root.querySelector(".gardener__panel");
  var launcher = root.querySelector("[data-gardener-open]");
  var closeBtn = root.querySelector("[data-gardener-close]");
  var clearBtn = root.querySelector("[data-gardener-clear]");
  var log = root.querySelector("[data-gardener-log]");
  var form = root.querySelector("[data-gardener-form]");
  var input = form.querySelector("input[name=message]");
  var sendBtn = form.querySelector("button[type=submit]");
  var chips = root.querySelector("[data-gardener-chips]");
  var statusLine = root.querySelector("[data-gardener-status]");
  var csrfInput = document.getElementById("csrf-token");
  var csrf = csrfInput ? csrfInput.value : "";
  var busy = false;
  var historyLoaded = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function safeUrl(url) {
    return typeof url === "string" && url.charAt(0) === "/" && url.charAt(1) !== "/" ? url : "#";
  }

  function scrollToEnd() {
    log.scrollTop = log.scrollHeight;
  }

  function jsonFetch(url, options) {
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return { ok: false, reply: "Something went wrong. Please try again." }; })
        .then(function (data) { data._status = response.status; return data; });
    }).catch(function () {
      return { ok: false, reply: "I could not reach the store. Please check your connection and try again." };
    });
  }

  function postJson(url, body) {
    return jsonFetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body || {})
    });
  }

  /* ---------- open / close ---------- */

  function openPanel() {
    panel.hidden = false;
    root.classList.add("is-open");
    if (launcher) launcher.setAttribute("aria-expanded", "true");
    ensureHistory();
    input.focus();
  }

  function closePanel() {
    panel.hidden = true;
    root.classList.remove("is-open");
    if (launcher) { launcher.setAttribute("aria-expanded", "false"); launcher.focus(); }
  }

  if (launcher) launcher.addEventListener("click", function () { panel.hidden ? openPanel() : closePanel(); });
  if (closeBtn) closeBtn.addEventListener("click", closePanel);
  root.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !inline && !panel.hidden) closePanel();
  });

  /* ---------- rendering ---------- */

  function addMessage(role, text) {
    var bubble = el("div", "gardener__msg gardener__msg--" + role);
    String(text || "").split(/\n{2,}/).forEach(function (paragraph) {
      if (paragraph.trim()) bubble.appendChild(el("p", null, paragraph.trim()));
    });
    log.appendChild(bubble);
    scrollToEnd();
    return bubble;
  }

  function addBlock(node) {
    log.appendChild(node);
    scrollToEnd();
  }

  function showTyping() {
    var node = el("div", "gardener__msg gardener__msg--bot gardener__typing");
    node.setAttribute("aria-label", "The Gardener is typing");
    for (var i = 0; i < 3; i++) node.appendChild(el("span", "gardener__dot"));
    log.appendChild(node);
    scrollToEnd();
    return node;
  }

  function addToCartDirect(product, variant, button) {
    /* Button press goes straight to the normal cart endpoint; the result chip is the backend's answer. */
    button.disabled = true;
    jsonFetch(root.dataset.cartAdd, {
      method: "POST", credentials: "same-origin", body: new URLSearchParams({ variant_id: variant.variant_id, quantity: 1 }),
      headers: { "Accept": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "fetch" }
    }).then(function (res) {
      button.disabled = false;
      var ok = res.ok === true;
      var text = ok ? "Added " + product.name + " (" + variant.name + ") to your cart." : (res.message || "Could not add this item.");
      var chip = el("div", "gardener__action gardener__action--" + (ok ? "ok" : "fail"), (ok ? "✓ " : "! ") + text);
      chip.setAttribute("role", "status");
      addBlock(chip);
      if (ok) refreshCart();
    });
  }

  function productCard(product) {
    var card = el("article", "gardener__card");
    if (product.image_url) {
      var img = el("img", "gardener__card-img");
      img.src = safeUrl(product.image_url); img.alt = product.name; img.loading = "lazy";
      card.appendChild(img);
    }
    var body = el("div", "gardener__card-body");
    var title = el("a", "gardener__card-title", product.name);
    title.href = safeUrl(product.url);
    body.appendChild(title);
    var meta = (product.from_price ? "From " + product.from_price : "") + (product.in_stock ? "" : " · Out of stock");
    body.appendChild(el("span", "gardener__card-meta", meta));
    if (product.care_instructions) body.appendChild(el("span", "gardener__card-note", product.care_instructions.slice(0, 140)));
    (product.variants || []).slice(0, 4).forEach(function (v) {
      var row = el("div", "gardener__variant");
      row.appendChild(el("span", null, v.name + " · " + v.price + (v.in_stock ? (v.low_stock ? " · only " + v.stock + " left" : "") : " · out of stock")));
      if (v.in_stock) {
        var add = el("button", "gardener__mini", "Add to cart");
        add.type = "button";
        add.addEventListener("click", function () { addToCartDirect(product, v, add); });
        row.appendChild(add);
      }
      body.appendChild(row);
    });
    card.appendChild(body);
    return card;
  }

  function cartCard(cart) {
    var card = el("article", "gardener__card gardener__card--cart");
    var body = el("div", "gardener__card-body");
    body.appendChild(el("strong", null, cart.count ? "Your cart (" + cart.count + " items)" : "Your cart is empty"));
    (cart.lines || []).forEach(function (l) {
      var line = el("div", "gardener__line");
      line.appendChild(el("span", null, l.quantity + " × " + l.product + " (" + l.option + ")" + (l.in_stock ? "" : " · check stock")));
      line.appendChild(el("span", null, l.line_total));
      body.appendChild(line);
    });
    if (cart.count) {
      var totals = el("div", "gardener__line gardener__line--total");
      totals.appendChild(el("span", null, "Shipping " + cart.shipping + " · Total"));
      totals.appendChild(el("strong", null, cart.total));
      body.appendChild(totals);
      var link = el("a", "gardener__link", "Open cart"); link.href = safeUrl(cart.cart_url);
      body.appendChild(link);
    }
    card.appendChild(body);
    return card;
  }

  function orderCard(order) {
    var card = el("article", "gardener__card gardener__card--order");
    var body = el("div", "gardener__card-body");
    var title = el("a", "gardener__card-title", "Order " + order.order_number);
    title.href = safeUrl(order.url);
    body.appendChild(title);
    body.appendChild(el("span", "gardener__card-meta", order.status + " · Payment " + order.payment_status + " · " + order.total + " · " + order.placed_on));
    if (order.invoice_url) {
      var invoice = el("a", "gardener__link", "Download invoice");
      invoice.href = safeUrl(order.invoice_url);
      body.appendChild(invoice);
    }
    if (order.shipment) {
      var s = order.shipment;
      body.appendChild(el("span", "gardener__card-note", "Courier: " + (s.courier || "—") + (s.tracking_number ? " · Tracking " + s.tracking_number : "") + " · " + s.status));
      if (s.tracking_url) { var t = el("a", "gardener__link", "Track shipment"); t.href = s.tracking_url; t.rel = "noopener noreferrer"; t.target = "_blank"; body.appendChild(t); }
    } else if (order.shipment_note) {
      body.appendChild(el("span", "gardener__card-note", order.shipment_note));
    }
    card.appendChild(body);
    return card;
  }

  function couponCard(data) {
    var coupon = data.coupon;
    var card = el("article", "gardener__card gardener__card--coupon");
    var body = el("div", "gardener__card-body");
    body.appendChild(el("strong", "gardener__card-title", "Coupon " + coupon.code));
    if (coupon.description) body.appendChild(el("span", "gardener__card-note", coupon.description));
    body.appendChild(el("span", "gardener__card-meta", coupon.discount_type + " · " + coupon.discount));
    var link = el("a", "gardener__link", "Recheck at checkout");
    link.href = safeUrl(data.checkout_url);
    body.appendChild(link);
    card.appendChild(body);
    return card;
  }

  function confirmCard(confirmation) {
    var card = el("div", "gardener__confirm");
    card.setAttribute("role", "group");
    card.setAttribute("aria-label", "Confirmation needed");
    card.appendChild(el("p", null, confirmation.prompt));
    var cancelling = confirmation.action === "cancel_order";
    var yes = el("button", cancelling ? "gardener__btn gardener__btn--danger" : "gardener__btn",
      cancelling ? "Yes, cancel order" : "Confirm change");
    var no = el("button", "gardener__btn", cancelling ? "Keep order" : "Don't change");
    yes.type = no.type = "button";
    function decide(decision) {
      yes.disabled = no.disabled = true;
      postJson(root.dataset.confirm, { token: confirmation.token, decision: decision }).then(function (res) {
        card.remove();
        renderResult(res);
      });
    }
    yes.addEventListener("click", function () { decide("confirm"); });
    no.addEventListener("click", function () { decide("decline"); });
    card.appendChild(yes); card.appendChild(no);
    return card;
  }

  function refreshCart() {
    jsonFetch(root.dataset.cartApi, { credentials: "same-origin", headers: { "Accept": "application/json" } }).then(function (data) {
      if (typeof data.count === "number") {
        document.querySelectorAll("[data-cart-count]").forEach(function (n) { n.textContent = data.count; });
      }
      document.dispatchEvent(new CustomEvent("gachghar:cart-changed"));
    });
  }

  function renderResult(res) {
    if (res.mode === "basic") statusLine.textContent = "Basic mode (AI not connected)";
    else if (res.mode === "ai") statusLine.textContent = "AI online";
    if (res.reply) addMessage("bot", res.reply);
    (res.actions || []).forEach(function (a) {
      var chip = el("div", "gardener__action gardener__action--" + (a.ok ? "ok" : "fail"), (a.ok ? "✓ " : "! ") + a.text);
      chip.setAttribute("role", "status");
      addBlock(chip);
    });
    if (res.products && res.products.length) {
      var strip = el("div", "gardener__cards");
      res.products.forEach(function (p) { strip.appendChild(productCard(p)); });
      addBlock(strip);
    }
    if (res.cart) addBlock(cartCard(res.cart));
    (res.orders || []).forEach(function (o) { addBlock(orderCard(o)); });
    if (res.coupon) addBlock(couponCard(res.coupon));
    (res.links || []).forEach(function (l) {
      var a = el("a", "gardener__link gardener__link--block", l.label); a.href = safeUrl(l.url); addBlock(a);
    });
    if (res.confirmation) addBlock(confirmCard(res.confirmation));
    if ((res.mutated || []).indexOf("cart") !== -1) refreshCart();
  }

  /* ---------- sending ---------- */

  function setBusy(state) {
    busy = state;
    sendBtn.disabled = state;
    input.disabled = state;
    log.setAttribute("aria-busy", String(state));
  }

  function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    if (chips) { chips.remove(); chips = null; }
    addMessage("user", text);
    input.value = "";
    setBusy(true);
    var typing = showTyping();
    postJson(root.dataset.api, { message: text }).then(function (res) {
      typing.remove();
      setBusy(false);
      if (res.ok === false && !res.actions) {
        addMessage("bot", res.reply || "Something went wrong. Please try again.");
      } else {
        renderResult(res);
      }
      input.focus();
    });
  }

  form.addEventListener("submit", function (event) { event.preventDefault(); send(input.value); });
  if (chips) {
    chips.addEventListener("click", function (event) {
      var chip = event.target.closest(".gardener__chip");
      if (chip) send(chip.textContent);
    });
  }

  clearBtn.addEventListener("click", function () {
    postJson(root.dataset.clear, {}).then(function () {
      log.querySelectorAll(".gardener__msg:not([data-gardener-welcome]), .gardener__cards, .gardener__card, .gardener__action, .gardener__confirm, .gardener__link--block").forEach(function (n) { n.remove(); });
      input.focus();
    });
  });

  /* ---------- restore this session's conversation ---------- */

  function ensureHistory() {
    if (historyLoaded) return;
    historyLoaded = true;
    jsonFetch(root.dataset.history, { credentials: "same-origin", headers: { "Accept": "application/json" } }).then(function (data) {
      if (!data.ok) return;
      statusLine.textContent = data.ai_configured ? "AI configured" : "Basic mode (AI not connected)";
      if (data.history && data.history.length && chips) { chips.remove(); chips = null; }
      (data.history || []).forEach(function (m) { addMessage(m.role === "user" ? "user" : "bot", m.content); });
    });
  }

  if (inline) ensureHistory();
})();
