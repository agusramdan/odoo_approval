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

        // Tampilkan notifikasi toast ke user
        this.do_notify(
            "Approval Update",
            "Ada pembaruan pada data persetujuan (Approval Task)."
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


    _scheduleReload: function () {
        var self = this;
        clearTimeout(this.reloadTimer);
        console.log("User tidak melihat approval.task");
        this.reloadTimer = setTimeout(function () {
            self._reloadView();
        }, 500);
    },

    _reloadView: function () {
        var actionManager = this.action_manager;
        if (actionManager){
            if (typeof actionManager.reload === 'function') {
                console.log("Melakukan refresh view approval.task...");
                actionManager.reload();
                return
            }

            if (typeof actionManager.getCurrentController === 'function') {
                var controller = actionManager.getCurrentController();
                // Cek apakah controller aktif memiliki widget view dan fungsi reload
                if (controller && controller.widget && typeof controller.widget.reload === 'function') {
                    console.log("Melakukan refresh data via Aktif Controller...");
                    // Perintahkan widget (List Controller / Form Controller) untuk reload data database
                    controller.widget.reload();
                    return;
                }
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
