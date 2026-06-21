odoo.define('amr_approval_live_refresh.live_refresh', function (require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var WebClient = require('web.WebClient'); // Ambil WebClient dasar

WebClient.include({
    // Override fungsi custom_events atau init untuk mendaftarkan bus
    show_application: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self._initApprovalBus();
        });
    },

    _initApprovalBus: function () {
        var self = this;
        this.channel = "approval.refresh.task.user." + session.uid;
        console.log("Bus otomatis aktif untuk channel:", this.channel);
        // Daftarkan channel dan pasang listener ke bus_service milik WebClient
        this.call('bus_service', 'addChannel', this.channel);
        this.call('bus_service', 'onNotification', this, this._onBusNotification);
    },

    _onBusNotification: function (notifications) {
        var self = this;
        notifications.forEach(function (notification) {
            var channel = notification[0];
            var payload = notification[1];
            console.log("Notifikasi masuk dari channel:", channel);
            // Validasi apakah channel sesuai
            if (channel === self.channel) {
                // Di Odoo 13, payload biasanya berbentuk objek jika dikirim via Python
                self._handleEvent(payload);
            }
        });
    },

    _handleEvent: function (payload) {
        console.log("Live refresh memproses payload:", payload);

        // Ambil data dinamis dari payload agar pesan lebih informatif (jika ada)
        var taskName = payload && payload.task_name ? payload.task_name : "New Task";
        var sender = payload && payload.sender_name ? " dari " + payload.sender_name : "";
        var message = payload && payload.message ? payload.message : "Change status approval.";

        // Gabungkan pesan menggunakan HTML + FontAwesome Icon agar menarik
        var notificationHTML =
            '<div class="d-flex align-items-start">' +
                '<i class="fa fa-bell fa-lg text-primary mr-3 mt-1"></i>' +
                '<div>' +
                    '<strong style="color: #00A09D;">' + taskName + '</strong>' + sender + '<br/>' +
                    '<small class="text-muted">' + message + '</small>' +
                '</div>' +
            '</div>';

        // Tampilkan notifikasi toast dengan hiasan HTML
        this.do_notify(
            "Update Approval", // Judul Notifikasi
            notificationHTML,  // Konten Notifikasi (HTML)
            false              // Parameter ketiga false agar tidak dianggap teks mentah (sticky/opsi bisa ditambahkan)
        );

        // Cek apakah user saat ini sedang melihat list/form 'approval.task'
        if (this._isApprovalTaskView()) {
            this._scheduleReload();
        }else{
            console.log("User tidak melihat approval.task");
        }
    },

    _isApprovalTaskView: function () {
        var actionManager = this.action_manager;

        // 1. Validasi awal keberadaan Action Manager
        if (!actionManager || !actionManager.getCurrentAction || !actionManager.getCurrentController) {
            return false;
        }

        var action = actionManager.getCurrentAction();
        var controller = actionManager.getCurrentController();

        // 2. Pastikan action dan controller saat ini tidak kosong
        if (!action || !controller) {
            return false;
        }

        // 3. Ambil tipe view yang sedang aktif (misal: 'list', 'form', 'kanban')
        var currentViewType = controller.viewType;

        console.log("Model Aktif: " + action.res_model);
        console.log("Tipe View Aktif: " + currentViewType);

        //Melakukan pengecekan ganda: Model harus sesuai DAN tipenya wajib 'list' atau 'tree'
        return action.res_model === "approval.task" && (currentViewType === "list" || currentViewType === "tree");
    },

    _isUserTyping: function () {
        // Cari elemen input search box Odoo 13 di dalam DOM
        var $searchInout = $('.o_searchview_input');

        // Jika elemen ditemukan dan sedang dalam posisi fokus (user sedang mengetik)
        if ($searchInout.length && $searchInout.is(':focus')) {
            console.log("Reload ditunda: User sedang aktif mengetik di Search Box.");
            return true;
        }
        return false;
    },

    _isModalOpen: function () {
        // Memeriksa apakah ada elemen dengan class .modal yang sedang tampil (visible)
        var $modal = $('.modal:visible');

        if ($modal.length > 0) {
            console.log("Reload ditunda: Jendela pop-up (Wizard Form) sedang terbuka.");
            return true;
        }
        return false;
    },

    _scheduleReload: function () {
        var self = this;

        // Bersihkan timer lama jika ada
        clearTimeout(this.reloadTimer);

        // KONDISI PENUNDAAN:
        // 1. User sedang mengetik di Search Box ATAU
        // 2. Ada jendela pop-up/wizard yang sedang terbuka
        if (this._isUserTyping() || this._isModalOpen()) {
            console.log("Menjadwalkan ulang reload dalam 3 detik karena user sedang sibuk...");

            this.reloadTimer = setTimeout(function () {
                self._scheduleReload(); // Cek kembali secara berkala (rekursif)
            }, 3000); // Cek ulang setiap 3 detik
            return;
        }

        // Jika kondisi aman (tidak mengetik & tidak ada pop-up), jalankan reload
        this.reloadTimer = setTimeout(function () {
            self._reloadView();
        }, 500);
    },

    _reloadView: function () {
        // Batalkan reload jika user sedang mengetik
        if (this._isUserTyping() || this._isModalOpen()) {
            console.log("User typing abort");
            return;
        }
        var actionManager = this.action_manager;
        if (actionManager && typeof actionManager.getCurrentController === 'function') {
            var controller = actionManager.getCurrentController();

            if (controller && controller.widget && typeof controller.widget.reload === 'function') {
                console.log("Melakukan refresh data List View dengan mempertahankan filter asli Odoo 13...");

                var listWidget = controller.widget;

                // Mengambil state internal runtime database yang sedang aktif di layar saat ini
                var currentDomain = [];
                var currentContext = {};

                if (listWidget.model && listWidget.handle) {
                    var modelState = listWidget.model.get(listWidget.handle);
                    if (modelState) {
                        // Ambil domain dan context asli hasil kalkulasi search view + filter bawaan action
                        currentDomain = modelState.domain || [];
                        currentContext = modelState.context || {};
                        console.log("Berhasil mengunci filter aktif:", currentDomain);
                    }
                }

                // Jalankan reload menggunakan domain & context asli yang terdeteksi
                listWidget.reload({
                    domain: currentDomain,
                    context: currentContext
                }).then(function () {
                    // EFEK VISUAL: Cari semua baris data di tabel aktif
                    var $rows = $('.o_list_view .o_data_row');
                    if ($rows.length > 0) {
                        $rows.addClass('row-animated-flash');
                        setTimeout(function () {
                            $rows.removeClass('row-animated-flash');
                        }, 2000);
                    }
                });
                return;
            }
        }
        // Jika gagal, gunakan Fallback ke metode alternatif ke-2
        this._fallbackClientReload();
    },

    _fallbackClientReload: function () {
        console.log("Menjalankan fallback client action reload...");
        this.do_action({
            type: 'ir.actions.client',
            tag: 'reload',
        });
    }

});

});
