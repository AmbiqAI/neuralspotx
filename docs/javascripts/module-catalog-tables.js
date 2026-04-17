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
    return Boolean(heading && heading.textContent.trim() === "Module Catalog");
  }

  function initDataTables() {
    var DataTable = window.simpleDatatables && window.simpleDatatables.DataTable;
    if (!DataTable || !isModuleCatalogPage()) {
      return;
    }

    var tables = document.querySelectorAll(".md-content table");
    tableConfigs.forEach(function (config, index) {
      var table = tables[index];
      if (!table || table.dataset.nsxDatatable === "true") {
        return;
      }

      table.dataset.nsxDatatable = "true";
      new DataTable(table, {
        searchable: true,
        paging: true,
        perPage: config.perPage,
        perPageSelect: config.perPageSelect,
        sortable: true,
        fixedHeight: false
      });

      var wrapper = table.closest(".datatable-wrapper");
      var searchInput = wrapper && wrapper.querySelector("input.datatable-input[type='search']");
      if (searchInput) {
        searchInput.placeholder = config.placeholder;
        searchInput.setAttribute("aria-label", config.placeholder);
      }

      var selector = wrapper && wrapper.querySelector("select.datatable-selector");
      if (selector) {
        selector.setAttribute("aria-label", "Rows per page");
      }
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
