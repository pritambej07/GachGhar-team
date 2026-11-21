/* GachGhar storefront behaviour. Vanilla JavaScript, no dependencies.
   Every server-side change (cart, wishlist, assistant) waits for the backend response before the UI reports success. */
(function () {
  "use strict";

  var overlay = document.querySelector("[data-overlay]");
  var csrfInput = document.getElementById("csrf-token");
  var csrf = csrfInput ? csrfInput.value : "";
  var openPanel = null;
  var returnFocus = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function json(response) {
    return response.json().catch(function () {
      return { ok: false, message: "Something went wrong. Please try again." };
    });
  }

  function post(url, data) {
    var body = new URLSearchParams(data || {});
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: body,
      headers: { "Accept": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "fetch" }
    }).then(json);
  }

  /* ---------- drawers and overlay ---------- */

  function focusables(panel) {
    return Array.prototype.slice.call(panel.querySelectorAll("a[href], button:not([disabled]), input, select, textarea"))
      .filter(function (node) { return node.offsetParent !== null; });
  }

  function openDrawer(panel, opener) {
    closeDrawer();
    returnFocus = opener || document.activeElement;
    panel.hidden = false;
    overlay.hidden = false;
    document.body.classList.add("is-locked");
    openPanel = panel;
    if (opener) opener.setAttribute("aria-expanded", "true");
    var first = focusables(panel)[0];
    if (first) first.focus();
  }

  function closeDrawer() {
    if (!openPanel) return;
    var id = openPanel.id;
    openPanel.hidden = true;
    overlay.hidden = true;
    document.body.classList.remove("is-locked");
    document.querySelectorAll('[aria-controls="' + id + '"]').forEach(function (node) {
      node.setAttribute("aria-expanded", "false");
    });
    openPanel = null;
    if (returnFocus && returnFocus.focus) returnFocus.focus();
    returnFocus = null;
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-drawer-open]");
    if (opener) {
      event.preventDefault();
      openDrawer(document.getElementById(opener.getAttribute("data-drawer-open")), opener);
      return;
    }
    if (event.target.closest("[data-cart-open]")) {
      event.preventDefault();
      openDrawer(document.getElementById("cart-drawer"), event.target.closest("[data-cart-open]"));
      loadCart();
      return;
    }
    if (event.target.closest("[data-drawer-close]") || event.target === overlay) {
      closeDrawer();
      return;
    }
    var toggle = event.target.closest("[data-search-toggle]");
    if (toggle) {
      var panel = document.getElementById("mobile-search");
      var open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      if (open) panel.querySelector("input").focus();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (!openPanel) return;
    if (event.key === "Escape") {
      closeDrawer();
    } else if (event.key === "Tab") {
      var items = focusables(openPanel);
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });

  /* ---------- cart ---------- */

  function setCartCount(count) {
    document.querySelectorAll("[data-cart-count]").forEach(function (node) { node.textContent = count; });
    document.querySelectorAll("[data-cart-open]").forEach(function (node) {
      node.setAttribute("aria-label", "Open cart, " + count + " items");
    });
  }

  function setMessage(container, message, ok) {
    var old = container.querySelector(".drawer-message");
    if (old) old.remove();
    if (!message) return;
    var note = el("div", "flash " + (ok ? "flash--success" : "flash--error") + " drawer-message", message);
    note.setAttribute("role", "status");
    container.insertBefore(note, container.firstChild);
  }

  function renderCart(data, message) {
    var body = document.querySelector("[data-cart-body]");
    var foot = document.querySelector("[data-cart-foot]");
    body.textContent = "";
    if (message) setMessage(body, message, data.ok !== false);
    if (!data.lines || !data.lines.length) {
      body.appendChild(el("p", "muted", "Your cart is empty."));
      foot.hidden = true;
      return;
    }
    var list = el("ul", "cart-drawer-list");
    data.lines.forEach(function (line) {
      var item = el("li", "cart-item" + (line.available && line.in_stock ? "" : " is-warning"));
      if (line.image_url) {
        var img = el("img", "cart-item__img");
        img.src = line.image_url; img.alt = ""; img.width = 64; img.height = 64;
        item.appendChild(img);
      }
      var info = el("div", "cart-item__info");
      var link = el("a", null, line.name);
      link.href = line.url;
      info.appendChild(link);
      info.appendChild(el("p", "muted", line.variant + " · " + line.unit_price));
      if (!line.available) info.appendChild(el("p", "error-text", "No longer available."));
      else if (!line.in_stock) info.appendChild(el("p", "error-text", "Only " + line.stock + " left."));
      var controls = el("div", "qty-mini");
      controls.appendChild(qtyButton("−", line.id, line.quantity - 1, "Decrease quantity"));
      controls.appendChild(el("span", "qty-mini__count", String(line.quantity)));
      controls.appendChild(qtyButton("+", line.id, line.quantity + 1, "Increase quantity"));
      var remove = el("button", "link-btn", "Remove");
      remove.type = "button";
      remove.setAttribute("data-cart-update", "");
      remove.dataset.itemId = line.id;
      remove.dataset.qty = "0";
      controls.appendChild(remove);
      info.appendChild(controls);
      item.appendChild(info);
      item.appendChild(el("p", "cart-item__total", line.line_total));
      list.appendChild(item);
    });
    body.appendChild(list);
    document.querySelector("[data-cart-subtotal]").textContent = data.subtotal;
    foot.hidden = false;
  }

  function qtyButton(label, itemId, qty, aria) {
    var button = el("button", "qty-mini__btn", label);
    button.type = "button";
    button.setAttribute("aria-label", aria);
    button.setAttribute("data-cart-update", "");
    button.dataset.itemId = itemId;
    button.dataset.qty = String(qty);
    return button;
  }

  function loadCart(message) {
    var body = document.querySelector("[data-cart-body]");
    fetch(body.dataset.api, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(json)
      .then(function (data) {
        setCartCount(data.count);
        renderCart(data, message);
      });
  }

  /* The AI Gardener fires this after the backend confirms a cart change, so the drawer and badge stay accurate. */
  document.addEventListener("gachghar:cart-changed", function () { loadCart(); });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-cart-update]");
    if (!button) return;
    event.preventDefault();
    var body = document.querySelector("[data-cart-body]");
    var url = body.dataset.updateUrl.replace("/0/", "/" + button.dataset.itemId + "/");
    post(url, { quantity: button.dataset.qty }).then(function (data) {
      setCartCount(data.count);
      renderCart(data, data.message);
    });
  });

  function setFormMessage(form, message, ok) {
    var note = form.querySelector(".form-message");
    if (!note) {
      note = el("p", "form-message");
      note.setAttribute("role", "status");
      form.appendChild(note);
    }
    note.textContent = message;
    note.className = "form-message " + (ok ? "flash flash--success" : "error-text");
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.matches("[data-cart-form]")) {
      event.preventDefault();
      var data = new FormData(form, event.submitter || undefined);
      fetch(form.action, { method: "POST", credentials: "same-origin", body: data,
        headers: { "Accept": "application/json", "X-Requested-With": "fetch" } })
        .then(json)
        .then(function (res) {
          if (res.redirect) { window.location.href = res.redirect; return; }
          if (res.ok) {
            setCartCount(res.count);
            setFormMessage(form, res.message, true);
            renderCart(res, res.message);
            openDrawer(document.getElementById("cart-drawer"), form.querySelector("button"));
          } else {
            setFormMessage(form, res.message, false);
          }
        });
    }
  });

  /* ---------- wishlist, gallery, product options ---------- */

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-wishlist-toggle]");
    if (toggle) {
      post(toggle.dataset.wishlistToggle).then(function (res) {
        if (!res.ok) return;
        toggle.setAttribute("aria-pressed", String(res.in_wishlist));
        toggle.textContent = res.in_wishlist ? "Saved to wishlist" : "Save to wishlist";
      });
      return;
    }
    var thumb = event.target.closest("[data-thumb]");
    if (thumb) {
      var main = document.getElementById("pdp-main");
      if (main) { main.src = thumb.dataset.src; main.alt = thumb.dataset.alt; }
      document.querySelectorAll("[data-thumb]").forEach(function (node) {
        node.setAttribute("aria-current", node === thumb ? "true" : "false");
      });
      return;
    }
    var step = event.target.closest("[data-step]");
    if (step) {
      var qty = document.getElementById("qty");
      var next = parseInt(qty.value, 10) + parseInt(step.dataset.step, 10);
      qty.value = String(Math.min(Math.max(next, 1), parseInt(qty.max, 10) || 1));
    }
  });

  document.addEventListener("change", function (event) {
    if (!event.target.matches('input[name="variant_id"]')) return;
    var radio = event.target;
    var stock = parseInt(radio.dataset.stock, 10);
    var discount = parseInt(radio.dataset.discount, 10);
    document.getElementById("pdp-price").textContent = radio.dataset.price;
    var compare = document.getElementById("pdp-compare");
    var badge = document.getElementById("pdp-discount");
    compare.textContent = radio.dataset.compare;
    compare.hidden = !discount;
    badge.hidden = !discount;
    badge.textContent = discount + "% off";
    var line = document.getElementById("stock-line");
    line.textContent = stock === 0 ? "Out of stock" : (radio.dataset.low === "1" ? "Only " + stock + " left" : "In stock");
    document.getElementById("add-btn").disabled = stock === 0;
    var qty = document.getElementById("qty");
    qty.max = String(Math.max(1, Math.min(stock, parseInt(qty.max, 10) || stock)));
    if (parseInt(qty.value, 10) > parseInt(qty.max, 10)) qty.value = qty.max;
  });

  /* ---------- password show/hide ---------- */

  document.querySelectorAll('input[type="password"]').forEach(function (input) {
    var button = el("button", "link-btn password-toggle", "Show password");
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide password" : "Show password";
      button.setAttribute("aria-pressed", String(show));
    });
    input.insertAdjacentElement("afterend", button);
  });

})();
