(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var search = document.querySelector("[data-gachghar-search]");
    if (!search) return;
    var summary = search.querySelector("summary");
    var input = search.querySelector('input[name="q"]');
    var form = search.querySelector("[data-product-search-form]");
    var close = search.querySelector("[data-search-close]");
    function closeSearch() {
      search.open = false;
      if (summary) summary.focus();
    }
    if (close) {
      close.addEventListener("click", closeSearch);
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && search.open) {
        closeSearch();
      }
    });
    document.addEventListener("click", function (event) {
      if (search.open && !search.contains(event.target)) {
        search.open = false;
      }
    });
    search.addEventListener("toggle", function () {
      if (search.open && input) {
        input.focus();
      }
    });
    if (form && input) {
      form.addEventListener("submit", function (event) {
        var query = input.value.trim();
        if (query.length < 2) {
          event.preventDefault();
          input.setCustomValidity("Please enter at least 2 characters.");
          input.reportValidity();
          input.focus();
          return;
        }
        input.setCustomValidity("");
        input.value = query;
      });

    var suggestionsBox = document.querySelector("[data-search-suggestions]");
    var debounceTimer;
    var DEBOUNCE_DELAY = 300;  // milliseconds

    function renderSuggestions(suggestions) {
      if (!suggestionsBox) return;
      suggestionsBox.innerHTML = "";
      if (suggestions.length === 0) {
        suggestionsBox.innerHTML = '<div class="no-results">No products found. Type more letters to search.</div>';
        return;
      }
      suggestions.forEach(function(item) {
        var option = document.createElement("a");
        option.href = item.url;
        option.className = "search-suggestion";
        option.setAttribute("role", "option");
        option.setAttribute("aria-label", item.name + " - ₹" + item.price);
        if (item.image_url) {
          var image = document.createElement("img");
          image.src = item.image_url;
          image.alt = item.name;
          image.loading = "lazy";
          image.dataset.imageFallback = "";
          var imageFallback = document.createElement("span");
          imageFallback.className = "search-suggestion__initial";
          imageFallback.textContent = item.name.slice(0, 1);
          imageFallback.hidden = true;
          imageFallback.setAttribute("aria-hidden", "true");
        } else {
          var imageFallback = document.createElement("span");
          imageFallback.className = "search-suggestion__initial";
          imageFallback.textContent = item.name.slice(0, 1);
          imageFallback.setAttribute("aria-hidden", "true");
        }
        imageFallback.dataset.imageFallbackPlaceholder = "";
        var info = document.createElement("div");
        info.className = "suggestion-info";
        var name = document.createElement("span");
        name.className = "suggestion-name";
        name.textContent = item.name;
        var price = document.createElement("span");
        price.className = "suggestion-price";
        price.textContent = "₹" + item.price;
        if (!item.in_stock) price.classList.add("out-of-stock");
        info.appendChild(name);
        info.appendChild(price);
        if (item.image_url) option.appendChild(image);
        option.appendChild(imageFallback);
        option.appendChild(info);
        suggestionsBox.appendChild(option);
      });
    }

    function fetchSuggestions(query) {
      if (query.length < 2) { renderSuggestions([]); return; }
      fetch(search.action + "search/suggestions/?q=" + encodeURIComponent(query), {
        headers: { "Accept": "application/json" }
      }).then(function(r) { return r.json(); }).then(function(d) { renderSuggestions(d.suggestions); }).catch(function() { renderSuggestions([]); });
    }

    input.addEventListener("input", function () {
      input.setCustomValidity("");
      clearTimeout(debounceTimer);
      var query = input.value.trim();
      if (query.length >= 2) {
        debounceTimer = setTimeout(function() { fetchSuggestions(query); }, DEBOUNCE_DELAY);
      } else {
        renderSuggestions([]);
      }
    });
    }
  });
})();
