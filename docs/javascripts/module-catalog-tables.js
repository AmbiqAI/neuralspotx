(function () {
  var tableConfigs = [
    {
      placeholder: "Search built-in modules...",
      perPage: 10,
      perPageSelect: [5, 10, 15, 25]
    },
    {
      placeholder: "Search board modules...",
      perPage: 5,
      perPageSelect: [5, 10, 15]
    }
  ];

  function isModuleCatalogPage() {
    var heading = document.querySelector(".md-content h1");
    return (
      /\/user-guide\/module-catalog\/?$/.test(window.location.pathname) ||
      Boolean(heading && heading.textContent.trim() === "Module Catalog")
    );
  }

  function createElement(tagName, className, text) {
    var node = document.createElement(tagName);
    if (className) {
      node.className = className;
    }
    if (typeof text === "string") {
      node.textContent = text;
    }
    return node;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function paginationItems(currentPage, totalPages) {
    var items = [];
    for (var page = 1; page <= totalPages; page += 1) {
      if (
        page === 1 ||
        page === totalPages ||
        (page >= currentPage - 1 && page <= currentPage + 1)
      ) {
        items.push(page);
      } else if (items[items.length - 1] !== "...") {
        items.push("...");
      }
    }
    return items;
  }

  function enhanceTable(table, config) {
    if (!table || table.dataset.nsxDatatable === "true") {
      return;
    }

    var tbody = table.tBodies[0];
    if (!tbody) {
      return;
    }

    table.dataset.nsxDatatable = "true";
    table.classList.add("datatable-table", "dataTable-table");

    var tableHost =
      table.closest(".md-typeset__scrollwrap") ||
      table.closest(".md-typeset__table") ||
      table;

    var wrapper = createElement("div", "datatable datatable-wrapper");
    var top = createElement("div", "datatable-top");
    var bottom = createElement("div", "datatable-bottom");
    var container = createElement("div", "datatable-container dataTable-container");
    var info = createElement("div", "datatable-info");
    var pagination = createElement("nav", "datatable-pagination");
    var paginationList = createElement("ul", "datatable-pagination-list");
    var dropdown = createElement("div", "datatable-dropdown");
    var dropdownLabel = createElement("label");
    var selector = createElement("select", "datatable-selector");
    var search = createElement("div", "datatable-search");
    var searchInput = createElement("input", "datatable-input");

    searchInput.type = "search";
    searchInput.placeholder = config.placeholder;
    searchInput.setAttribute("aria-label", config.placeholder);

    selector.setAttribute("aria-label", "Rows per page");
    config.perPageSelect.forEach(function (size) {
      var option = createElement("option");
      option.value = String(size);
      option.textContent = String(size);
      if (size === config.perPage) {
        option.selected = true;
      }
      selector.appendChild(option);
    });

    dropdownLabel.appendChild(selector);
    dropdownLabel.appendChild(document.createTextNode(" entries per page"));
    dropdown.appendChild(dropdownLabel);
    search.appendChild(searchInput);
    pagination.appendChild(paginationList);
    top.appendChild(dropdown);
    top.appendChild(search);
    bottom.appendChild(info);
    bottom.appendChild(pagination);

    tableHost.parentNode.insertBefore(wrapper, tableHost);
    wrapper.appendChild(top);
    wrapper.appendChild(container);
    container.appendChild(tableHost);
    wrapper.appendChild(bottom);

    var rows = Array.prototype.slice.call(tbody.rows);
    var totalRows = rows.length;
    var emptyRow = createElement("tr", "datatable-empty");
    var emptyCell = createElement("td", null, "No matching entries found");
    emptyCell.colSpan = table.tHead && table.tHead.rows[0] ? table.tHead.rows[0].cells.length : 1;
    emptyRow.appendChild(emptyCell);

    var state = {
      currentPage: 1,
      perPage: config.perPage,
      term: ""
    };

    function filteredRows() {
      var term = state.term.trim().toLowerCase();
      if (!term) {
        return rows;
      }
      return rows.filter(function (row) {
        return row.textContent.toLowerCase().indexOf(term) !== -1;
      });
    }

    function renderPagination(totalPages) {
      paginationList.innerHTML = "";

      function addButton(label, targetPage, disabled, active, ellipsis) {
        var item = createElement(
          "li",
          [
            disabled ? "datatable-disabled" : "",
            active ? "datatable-active" : "",
            ellipsis ? "datatable-ellipsis" : ""
          ]
            .filter(Boolean)
            .join(" ")
        );
        var button = createElement("button", null, label);
        button.type = "button";
        button.disabled = Boolean(disabled || ellipsis);
        if (!button.disabled) {
          button.addEventListener("click", function () {
            state.currentPage = targetPage;
            render();
          });
        }
        item.appendChild(button);
        paginationList.appendChild(item);
      }

      addButton("Prev", state.currentPage - 1, state.currentPage === 1, false, false);
      paginationItems(state.currentPage, totalPages).forEach(function (item) {
        if (item === "...") {
          addButton("...", state.currentPage, true, false, true);
          return;
        }
        addButton(String(item), item, false, item === state.currentPage, false);
      });
      addButton("Next", state.currentPage + 1, state.currentPage === totalPages, false, false);
    }

    function render() {
      var filtered = filteredRows();
      var totalFiltered = filtered.length;
      var totalPages = Math.max(1, Math.ceil(totalFiltered / state.perPage));
      state.currentPage = clamp(state.currentPage, 1, totalPages);

      rows.forEach(function (row) {
        row.hidden = true;
      });

      if (emptyRow.parentNode === tbody) {
        tbody.removeChild(emptyRow);
      }

      if (totalFiltered === 0) {
        tbody.appendChild(emptyRow);
        info.textContent = "Showing 0 to 0 of 0 entries";
        renderPagination(1);
        return;
      }

      var start = (state.currentPage - 1) * state.perPage;
      var end = Math.min(start + state.perPage, totalFiltered);

      filtered.slice(start, end).forEach(function (row) {
        row.hidden = false;
      });

      info.textContent =
        "Showing " +
        String(start + 1) +
        " to " +
        String(end) +
        " of " +
        String(totalFiltered) +
        (totalFiltered !== totalRows ? " entries (filtered from " + String(totalRows) + " total)" : " entries");

      renderPagination(totalPages);
    }

    searchInput.addEventListener("input", function () {
      state.term = searchInput.value;
      state.currentPage = 1;
      render();
    });

    selector.addEventListener("change", function () {
      var parsed = Number(selector.value);
      if (!Number.isNaN(parsed) && parsed > 0) {
        state.perPage = parsed;
        state.currentPage = 1;
        render();
      }
    });

    render();
  }

  function initDataTables() {
    if (!isModuleCatalogPage()) {
      return;
    }

    var tables = document.querySelectorAll(".md-content table");
    tableConfigs.forEach(function (config, index) {
      var table = tables[index];
      enhanceTable(table, config);
    });
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(function () {
      initDataTables();
    });
  } else {
    document.addEventListener("DOMContentLoaded", initDataTables);
  }
})();
