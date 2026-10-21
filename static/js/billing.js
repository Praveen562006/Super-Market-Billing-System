/* Point-of-Sale logic.
   The cart is only a convenience: prices, discounts, taxes and totals are
   recomputed on the server when the sale is submitted. */
(function () {
  "use strict";

  var state = { cart: {}, token: null };
  var els = {};

  function currency() {
    return (window.POS_CONFIG && window.POS_CONFIG.currency) || "\u20b9";
  }
  function fmt(value) {
    var n = Number(value || 0);
    return currency() + n.toFixed(2);
  }
  function roundMoney(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
  }
  function genToken() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "t" + Date.now() + Math.random().toString(16).slice(2);
  }

  function lineUnitPrice(product) {
    var price = Number(product.selling_price || 0);
    var discount = Number(product.discount_percent || 0);
    return price - price * discount / 100;
  }

  function renderProducts(products) {
    var grid = els.grid;
    grid.innerHTML = "";
    if (!products.length) {
      grid.innerHTML = '<div class="empty-state"><i class="bi bi-search"></i>No products found.</div>';
      return;
    }
    products.forEach(function (product) {
      var out = Number(product.stock_quantity) <= 0;
      var tile = document.createElement("button");
      tile.type = "button";
      tile.className = "product-tile" + (out ? " out" : "");
      tile.innerHTML =
        '<div class="name">' + escapeHtml(product.name) + "</div>" +
        '<div class="meta">' + escapeHtml(product.sku) +
        (product.category ? " &middot; " + escapeHtml(product.category) : "") + "</div>" +
        '<div class="price">' + fmt(product.selling_price) +
        (Number(product.discount_percent) ? ' <span class="badge badge-warn">-' + product.discount_percent + "%</span>" : "") +
        "</div>" +
        '<div class="meta">Stock: ' + product.stock_quantity + "</div>";
      if (!out) {
        tile.addEventListener("click", function () { addToCart(product); });
      }
      grid.appendChild(tile);
    });
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : text;
    return div.innerHTML;
  }

  function addToCart(product) {
    var id = product.id;
    var existing = state.cart[id];
    if (existing) {
      if (existing.quantity + 1 > product.stock_quantity) {
        window.alert("Not enough stock for " + product.name + ".");
        return;
      }
      existing.quantity += 1;
    } else {
      state.cart[id] = {
        id: id,
        name: product.name,
        sku: product.sku,
        unit_price: Number(product.selling_price || 0),
        discount_percent: Number(product.discount_percent || 0),
        tax_rate: Number(product.tax_rate || 0),
        stock_quantity: product.stock_quantity,
        quantity: 1,
      };
    }
    renderCart();
  }

  function setQuantity(id, qty) {
    var line = state.cart[id];
    if (!line) return;
    qty = parseInt(qty, 10);
    if (isNaN(qty) || qty <= 0) { delete state.cart[id]; renderCart(); return; }
    if (qty > line.stock_quantity) {
      window.alert("Only " + line.stock_quantity + " in stock for " + line.name + ".");
      qty = line.stock_quantity;
    }
    line.quantity = qty;
    renderCart();
  }

  function renderCart() {
    var body = els.cartBody;
    body.innerHTML = "";
    var ids = Object.keys(state.cart);
    if (!ids.length) {
      body.innerHTML = '<div class="empty-state" style="padding:24px"><i class="bi bi-cart-x"></i>Cart is empty</div>';
    }
    var subtotal = 0, discount = 0, tax = 0;
    ids.forEach(function (id) {
      var line = state.cart[id];
      var gross = roundMoney(line.unit_price * line.quantity);
      var lineDiscount = roundMoney(gross * line.discount_percent / 100);
      var net = gross - lineDiscount;
      var lineTax = roundMoney(net * line.tax_rate / 100);
      subtotal += gross; discount += lineDiscount; tax += lineTax;

      var row = document.createElement("div");
      row.className = "cart-line";
      row.innerHTML =
        '<div><div class="title">' + escapeHtml(line.name) + '</div>' +
        '<div class="sub">' + fmt(line.unit_price) + ' &middot; ' +
        (line.discount_percent ? "-" + line.discount_percent + "% &middot; " : "") +
        "Tax " + line.tax_rate + "%</div></div>" +
        '<div class="controls">' +
        '<input class="qty-input" type="number" min="1" max="' + line.stock_quantity + '" value="' + line.quantity + '">' +
        '<button class="btn btn-sm btn-danger" type="button" title="Remove">&times;</button></div>';
      var input = row.querySelector("input");
      input.addEventListener("change", function () { setQuantity(id, input.value); });
      row.querySelector("button").addEventListener("click", function () { delete state.cart[id]; renderCart(); });
      body.appendChild(row);
    });

    var billDiscountPct = getBillDiscountPct();
    var afterItem = subtotal - discount;
    var billDiscount = roundMoney(afterItem * billDiscountPct / 100);
    var grand = roundMoney(afterItem + tax - billDiscount);
    if (grand < 0) grand = 0;

    setText("sumSubtotal", fmt(subtotal));
    setText("sumDiscount", "-" + fmt(discount + billDiscount));
    setText("sumTax", fmt(tax));
    setText("sumTotal", fmt(grand));
    updateChange(grand);
    els.payBtn.disabled = ids.length === 0;
  }

  function getBillDiscountPct() {
    var value = parseFloat(els.billDiscount.value);
    if (isNaN(value) || value < 0) return 0;
    return value;
  }

  function updateChange(total) {
    var method = els.method.value;
    if (method !== "cash") {
      els.received.disabled = true;
      els.changeRow.style.display = "none";
      return;
    }
    els.received.disabled = false;
    els.changeRow.style.display = "";
    var received = parseFloat(els.received.value);
    var change = (!isNaN(received) ? received : 0) - total;
    setText("sumChange", fmt(change > 0 ? change : 0));
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function search() {
    var q = els.search.value.trim();
    var category = els.category.value;
    var params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    els.grid.innerHTML = '<div class="empty-state"><i class="bi bi-hourglass-split"></i>Loading...</div>';
    fetch((window.POS_CONFIG.searchUrl) + "?" + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (data) { renderProducts(data.products || []); })
      .catch(function () {
        els.grid.innerHTML = '<div class="empty-state"><i class="bi bi-exclamation-triangle"></i>Could not load products.</div>';
      });
  }

  function lookupCustomer() {
    if (!els.mobile) return;
    var mobile = els.mobile.value.trim();
    var digits = mobile.replace(/\D/g, "");
    if (!els.lookupStatus) {
      // no-op
    } else if (digits.length < 6) {
      els.lookupStatus.textContent = "Enter a number to find a registered buyer.";
    }

    if (digits.length < 6) return;

    fetch(window.POS_CONFIG.customerLookupUrl + "?mobile=" + encodeURIComponent(mobile))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.found && data.name) {
          els.customerName.value = data.name;
          if (els.lookupStatus) els.lookupStatus.textContent = "Registered buyer: " + data.name;
        } else if (els.lookupStatus) {
          els.lookupStatus.textContent = "New customer \u2014 name will be saved with this bill.";
        }
      })
      .catch(function () {
        if (els.lookupStatus) els.lookupStatus.textContent = "";
      });
  }

  function showReceipt(data) {
    setText("receiptInvoice", data.invoice_number || "\u2014");
    setText("receiptTotal", fmt(data.grand_total));

    var printBtn = document.getElementById("receiptPrint");
    if (printBtn) printBtn.href = data.print_url || data.invoice_url || "#";

    var viewBtn = document.getElementById("receiptView");
    if (viewBtn) viewBtn.href = data.invoice_url || "#";

    var waBtn = document.getElementById("receiptWhatsapp");
    var hint = document.getElementById("receiptHint");
    if (waBtn) {
      if (data.whatsapp_url) {
        waBtn.href = data.whatsapp_url;
        waBtn.classList.remove("d-none");
        if (hint) hint.textContent = "Print the bill or send it straight to the customer on WhatsApp.";
      } else {
        waBtn.removeAttribute("href");
        waBtn.classList.add("d-none");
        if (hint) hint.textContent = "No WhatsApp number was added, so only printing is available.";
      }
    }

    var modalEl = document.getElementById("checkoutModal");
    if (modalEl && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  }

  function checkout() {
    var ids = Object.keys(state.cart);
    if (!ids.length) { window.alert("Add at least one product."); return; }
    var method = els.method.value;
    var total = parseFloat(els.sumTotal.textContent.replace(currency(), "").replace(/,/g, "")) || 0;
    var received = parseFloat(els.received.value);
    if (method === "cash" && (isNaN(received) || received < total)) {
      window.alert("Amount received must be at least the total.");
      els.received.focus();
      return;
    }

    els.payBtn.disabled = true;
    els.payBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';

    window.apiPost(window.POS_CONFIG.checkoutUrl, {
      items: ids.map(function (id) { return { product_id: Number(id), quantity: state.cart[id].quantity }; }),
      payment_method: method,
      amount_received: method === "cash" ? received : total,
      customer_mobile: els.mobile.value.trim(),
      customer_name: els.customerName.value.trim(),
      bill_discount_percent: getBillDiscountPct(),
      client_token: state.token,
    }).then(function (result) {
      if (result.ok && result.data.success) {
        // Reset the cart and immediately offer the two delivery options.
        state.cart = {};
        state.token = genToken();
        els.received.value = "";
        els.billDiscount.value = "0";
        renderCart();
        showReceipt(result.data);
        els.payBtn.disabled = false;
        els.payBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Complete sale';
        return;
      }
      window.alert((result.data && result.data.message) || "Checkout failed.");
      els.payBtn.disabled = false;
      els.payBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Complete sale';
      state.token = genToken(); // allow a fresh attempt
    }).catch(function () {
      window.alert("A network error occurred.");
      els.payBtn.disabled = false;
      els.payBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Complete sale';
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    els.grid = document.getElementById("productGrid");
    if (!els.grid) return; // not on the POS page
    els.search = document.getElementById("posSearch");
    els.category = document.getElementById("posCategory");
    els.cartBody = document.getElementById("cartBody");
    els.method = document.getElementById("paymentMethod");
    els.received = document.getElementById("amountReceived");
    els.changeRow = document.getElementById("changeRow");
    els.mobile = document.getElementById("customerMobile");
    els.customerName = document.getElementById("customerName");
    els.lookupStatus = document.getElementById("customerLookupStatus");
    els.billDiscount = document.getElementById("billDiscount");
    els.sumTotal = document.getElementById("sumTotal");
    els.payBtn = document.getElementById("payBtn");

    state.token = genToken();
    els.search.addEventListener("input", debounce(search, 250));
    els.category.addEventListener("change", search);
    els.method.addEventListener("change", function () { renderCart(); });
    els.received.addEventListener("input", function () {
      var total = parseFloat(els.sumTotal.textContent.replace(currency(), "").replace(/,/g, "")) || 0;
      updateChange(total);
    });
    els.billDiscount.addEventListener("input", renderCart);
    els.mobile.addEventListener("input", debounce(lookupCustomer, 400));
    els.payBtn.addEventListener("click", checkout);

    document.getElementById("clearCart").addEventListener("click", function () {
      if (Object.keys(state.cart).length && !window.confirm("Clear the cart?")) return;
      state.cart = {};
      renderCart();
    });

    search();
    renderCart();
  });

  function debounce(fn, wait) {
    var handle;
    return function () {
      clearTimeout(handle);
      handle = setTimeout(fn, wait);
    };
  }
})();
