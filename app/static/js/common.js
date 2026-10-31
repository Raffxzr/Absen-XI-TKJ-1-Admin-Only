/* JS ringan: tema gelap/terang, konfirmasi tindakan, tampil/sembunyi kata sandi, cetak, hitung mundur sesi. Tanpa dependensi. */
(function () {
  "use strict";

  // Pengaturan tema (terang / gelap) disimpan di localStorage.
  var STORAGE_KEY = "absensi_theme";
  var root = document.documentElement;

  function getInitialTheme() {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "dark" || saved === "light") return saved;
    } catch (e) {}
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    var isDark = theme === "dark";
    root.setAttribute("data-theme", isDark ? "dark" : "light");
    var toggles = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      var btn = toggles[i];
      btn.setAttribute("aria-pressed", String(isDark));
      btn.setAttribute("aria-label", isDark ? "Ganti ke tema terang" : "Ganti ke tema gelap");
      var lbl = btn.querySelector("[data-theme-label]");
      if (lbl) lbl.textContent = isDark ? "Terang" : "Gelap";
    }
  }

  applyTheme(getInitialTheme());

  // Dialog konfirmasi untuk form dengan atribut data-confirm.
  var dialog = document.getElementById("confirm-dialog");
  var pending = null;
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var message = form.getAttribute && form.getAttribute("data-confirm");
    if (!message || !dialog || typeof dialog.showModal !== "function") return;
    if (form.dataset.confirmed === "1") return;
    e.preventDefault();
    pending = form;
    document.getElementById("confirm-message").textContent = message;
    var ok = document.getElementById("confirm-ok");
    ok.textContent = form.getAttribute("data-confirm-label") || "Lanjutkan";
    dialog.showModal();
  });
  if (dialog) {
    dialog.addEventListener("close", function () {
      if (dialog.returnValue === "ok" && pending) {
        pending.dataset.confirmed = "1";
        pending.submit();
      }
      pending = null;
      dialog.returnValue = "";
    });
  }

  // Klik tombol: ganti tema, tampil/sembunyi kata sandi, cetak, salin jadwal Senin.
  document.addEventListener("click", function (e) {
    var themeBtn = e.target.closest("[data-theme-toggle]");
    if (themeBtn) {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (err) {}
      return;
    }
    var btn = e.target.closest("[data-toggle-password]");
    if (btn) {
      var input = document.getElementById(btn.getAttribute("data-toggle-password"));
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", String(show));
      btn.setAttribute("aria-label", show ? "Sembunyikan kata sandi" : "Tampilkan kata sandi");
      return;
    }
    if (e.target.closest("[data-print]")) {
      window.print();
      return;
    }
    var copy = e.target.closest("[data-copy-monday]");
    if (copy) {
      var o = document.getElementById("sched_0_open").value, c = document.getElementById("sched_0_close").value;
      for (var i = 1; i <= 4; i++) {
        document.getElementById("sched_" + i + "_open").value = o;
        document.getElementById("sched_" + i + "_close").value = c;
      }
    }
  });

  // Hitung mundur sisa waktu sesi presensi; muat ulang saat habis agar status sesuai server.
  var cd = document.querySelector("[data-countdown]");
  if (cd) {
    var left = parseInt(cd.getAttribute("data-countdown"), 10);
    var render = function () {
      var h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
      cd.textContent = (h > 0 ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(s).padStart(2, "0");
    };
    render();
    var timer = setInterval(function () {
      left -= 1;
      if (left <= 0) { clearInterval(timer); window.location.reload(); return; }
      render();
    }, 1000);
  }
})();
