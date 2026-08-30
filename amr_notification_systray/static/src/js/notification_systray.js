odoo.define('amr_notification_systray.notification_systray', function (require) {
    "use strict";

    var Widget = require('web.Widget');
    var SystrayMenu = require('web.SystrayMenu');
    var rpc = require('web.rpc');

    var NotificationSystray = Widget.extend({
        template: 'amr_notification_systray.NotificationSystray',

        events: {
            // Kita gunakan event resmi Bootstrap yang didukung penuh oleh navbar Odoo 13
            'show.bs.dropdown': '_onDropdownShow',
            'click .o_notification_tab': '_onTabClick',
            'click .o_mail_preview': '_onNotificationClick',
            'click .o_notification_toggle_read': '_onToggleRead',
            'click .o_notification_action_approval': '_onActionApprovalShow'
        },

        init: function () {
            this._super.apply(this, arguments);

            this.notifications = [];
            this.unreadCount = 0;

            this.state = {
                unreadCount: 0,
                tab: 'unread',
            };

            this.limit = 20;
            this.offset = 0;
            this.isLoading = false;
            this.hasMore = true;
        },

        willStart: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                return self._fetchNotificationsData();
            });
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._bindNotificationBus();
                // TAMBAHKAN INI: Dengarkan klik di seluruh dokumen halaman
                // Menggunakan namespace agar aman saat dihancurkan (destroy)
                $(document).on('click.notification_systray', self._onWindowClick.bind(self));
            });
        },
        destroy: function () {
            // TAMBAHKAN INI: Bersihkan listener saat berpindah aplikasi/menu di Odoo
            $(document).off('click.notification_systray');
            this._super.apply(this, arguments);
        },
        /**
         * Menutup dropdown secara otomatis jika pengguna mengklik area luar widget
         */
        _onWindowClick: function (ev) {
            // Jika elemen widget ini sudah tidak ada di DOM, hentikan fungsi
            if (!this.$el || !this.$el.length) return;

            // Periksa apakah area yang diklik BUKAN bagian dari ikon bel atau kotak dropdown kita
            if (!this.$el.is(ev.target) && this.$el.has(ev.target).length === 0) {
                // Hapus kelas show dari bootstrap untuk menyembunyikannya
                this.$el.removeClass('show');
                this.$('.o_notification_bell').attr('aria-expanded', 'false');
                this.$('.o_notification_dropdown').removeClass('show');
            }
        },

        /**
         * Mendaftarkan channel privat khusus untuk User yang sedang login
         */
        _bindNotificationBus: function () {
            var session = require('web.session'); // Ambil library session Odoo
            var current_uid = session.uid;        // Ambil ID User yang sedang aktif

            if (!current_uid) {
                return; // Jaga-jaga jika session kosong atau belum login
            }

            // Menyusun nama channel unik untuk user tersebut
            var user_channel = 'notification_bus_user_' + current_uid;

            // Daftarkan channel privat ini ke dalam sistem Bus Odoo pusat agar didengarkan
            if (this.call) {
                console.log("Bus otomatis aktif untuk channel:", user_channel);
                this.call('bus_service', 'addChannel', user_channel);
                this.call('bus_service', 'onNotification', this, function (notifications) {
                    var self = this;
                    notifications.forEach(function (notif) {
                    var channel = notif[0];
                    var payload = notif[1];
                    console.log("Notifikasi masuk dari channel:", channel);
                        //notif[0] berisi nama channel, notif[1] berisi payload data dari Python
                        if (channel === user_channel) {
                            // Di Odoo 13, payload biasanya berbentuk objek jika dikirim via Python
                            self._onBusNotification(null, notif[1]);
                        }
                    });
                });
            }
        },
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                // Daftarkan event bus per user saat widget dimuat
                self._bindNotificationBus();

                $(document).on('click.notification_systray', self._onWindowClick.bind(self));
            });
        },

        /**
         * Dipicu otomatis secara realtime saat backend Python mengirim data baru via Bus
         */
        _onBusNotification: function (event, notification) {
            if (!notification) return;

            // 1. Cegah duplikasi data jika id notifikasi sudah ada di memori local browser
            var exists = _.find(this.notifications, function (item) {
                return item.id === notification.id;
            });

            if (exists) return;

            // 2. Tambahkan notifikasi baru ke baris paling atas (unshift)
            this.notifications.unshift(notification);

            // 3. Jika statusnya belum dibaca, naikkan angka unread count
            if (!notification.is_read) {
                this.unreadCount++;
                this.state.unreadCount = this.unreadCount;
            }

            // 4. TRIGGER UI UPDATE: Jalankan fungsi re-render aman
            // Ini akan memperbarui teks angka badge bel dan menyusun ulang konten list dropdown secara halus
            this._renderAndPreserveState();

            // (Opsional) Jika ingin memicu bunyi atau browser notification bawaan OS
            if (window.Notification && Notification.permission === "granted") {
                new Notification(notification.title, { body: notification.message });
            }
        },

        /**
         * Dipicu otomatis saat pengguna mengklik tombol bel Anda
         */
        _onDropdownShow: function (ev) {
            // Tambahkan baris ini jika parameter 'ev' dikirim oleh Bootstrap
            if (ev) {
                ev.stopPropagation();
            }
            this.offset = 0;
            var self = this;
            this._fetchNotificationsData().then(function() {
                self._renderAndPreserveState();
            });
        },

        _fetchNotificationsData: function () {
            var self = this;

            if (this.isLoading) {
                return Promise.resolve();
            }
            this.isLoading = true;

            return rpc.query({
                route: '/amr_notification_systray/notifications',
                params: {
                    limit: this.limit,
                    offset: this.offset,
                },
            })
            .then(function (result) {
                result = result || {};
                var records = result.notifications || [];
                self.unreadCount = result.unread_count || 0;

                if (self.offset === 0) {
                    self.notifications = records;
                } else {
                    self.notifications = self.notifications.concat(records);
                }

                self.hasMore = records.length >= self.limit;
                self.state.unreadCount = self.unreadCount;
            })
            .guardedCatch(function (error) {
                console.error('Failed to load notifications', error);
            })
            .finally(function () {
                self.isLoading = false;
            });
        },

        _renderAndPreserveState: function () {
            // Cek apakah dropdown dalam kondisi sedang terbuka sebelum dirender ulang
            var isOpen = this.$el.hasClass('show') || this.$('.o_notification_dropdown').hasClass('show');

            this.renderElement();

            // Kembalikan kelas aktif Bootstrap pasca re-render utuh widget
            if (isOpen) {
                this.$el.addClass('show');
                this.$('.o_notification_bell').attr('aria-expanded', 'true');
                this.$('.o_notification_dropdown').addClass('show');
            }
        },

        getFilteredNotifications: function () {
            if (this.state.tab === 'unread') {
                return _.filter(this.notifications, function (item) {
                    return !item.is_read;
                });
            }
            return this.notifications;
        },

        _onTabClick: function (ev) {
            ev.preventDefault();
            ev.stopPropagation(); // Kunci dropdown agar tetap terbuka saat tab diklik

            var $target = $(ev.currentTarget);
            this.state.tab = $target.data('tab');

            this._renderAndPreserveState();
        },

        _onNotificationClick: function (ev) {
            ev.preventDefault();
            // Jalankan rute buka dokumen kustom Anda di sini...
        },
        /**
         * Meng-invoke fungsi action_approval_show di backend Python Odoo 13
         * Mendukung ir.actions.act_window maupun ir.actions.act_url
         */
        _onActionApprovalShow: function (ev) {
            ev.preventDefault();
            ev.stopPropagation(); // Amankan agar dropdown tidak menutup tiba-tiba saat tombol diklik

            var self = this;
            var $button = $(ev.currentTarget);

            // Pastikan data-id yang diambil dari tombol XML adalah ID record NOTIFIKASI
            var resId = parseInt($button.data('id'));

            if (!resId) {
                console.error("ID Notifikasi tidak ditemukan pada atribut tombol!");
                return;
            }

            return this._rpc({
                model: 'notification.partner',
                method: 'action_approval_show',
                args: [[resId]], // Melemparkan ID Notifikasi agar dibaca oleh self.ensure_one() di Python
            })
            .then(function (action) {
                self.$el.removeClass('show');
                self.$('.o_mail_systray_dropdown').removeClass('show');
                self.$('.o_notification_dropdown').removeClass('show'); // Jaga-jaga jika kelas lama masih dipakai
                // Pastikan backend mengembalikan objek action yang valid
                if (action && typeof action === 'object') {

                    // Normalisasi darurat jika Python melewatkan parameter views
                    if (action.type === 'ir.actions.act_window') {
                        action.views = action.views || [[false, 'form']];
                        action.view_mode = action.view_mode || 'form';
                    }

                    // Tembakkan event do_action ke WebClient pusat Odoo 13
                    // === SOLUSI UTAMA BYPASS SYSTRAY ===
                    // Di Odoo 13, widget utama (WebClient) biasanya melekatkan ActionManager
                    // ke dalam parent chain atau core. Kita bisa panggil via fungsi do_action
                    // bawaan class Widget dasar yang otomatis merestart pencarian parent yang valid.
                    if (self.do_action) {
                        self.do_action(action, {
                            clear_breadcrumbs: false,
                        });
                    } else if (self.getParent() && self.getParent().do_action) {
                        self.getParent().do_action(action);
                    } else {
                        // Jika cara di atas gagal karena keterbatasan container,
                        // kita tembak via Event Bus global Odoo 13
                        core.bus.trigger('do_action', action);
                    }
                } else {
                    console.warn("Backend Python tidak mengembalikan format Action Window/URL yang sah:", action);
                }
            })
            .guardedCatch(function (error) {
                console.error("Gagal menjalankan fungsi approval backend", error);
            });
        },
        /**
         * Handler untuk melakukan toggle read status
         */
        _onToggleRead: function (ev) {
            ev.preventDefault();
            ev.stopPropagation(); // PENTING: Mencegah dropdown tertutup atau memicu '_onNotificationClick'

            var self = this;
            var $button = $(ev.currentTarget);
            var notificationId = $button.data('id');

            // 1. Cari objek notifikasi di array local memory untuk merubah status secara instan (UI responsif)
            var notification = _.find(this.notifications, function (item) {
                return item.id === notificationId;
            });

            if (!notification) return;

            // Balik status is_read (jika true jadi false, jika false jadi true)
            var newReadState = !notification.is_read;
            notification.is_read = newReadState;

            // 2. Sesuaikan angka Unread Count di Badge
            if (newReadState === true) {
                this.unreadCount = Math.max(0, this.unreadCount - 1);
            } else {
                this.unreadCount++;
            }
            this.state.unreadCount = this.unreadCount;

            // 3. Render ulang komponen agar UI langsung berubah (warna latar & ikon berganti)
            this._renderAndPreserveState();

            // 4. Kirim data perubahan status ini ke Python Backend lewat RPC Route
            return rpc.query({
                route: '/amr_notification_systray/toggle_read',
                params: {
                    notification_id: notificationId,
                    is_read: newReadState,
                },
            }).guardedCatch(function (error) {
                console.error('Failed to sync toggle read state to server', error);
                // Rollback status lokal jika server gagal merespon
                notification.is_read = !newReadState;
                if (newReadState === true) self.unreadCount++; else self.unreadCount--;
                self.state.unreadCount = self.unreadCount;
                self._renderAndPreserveState();
            });
        }
    });

    SystrayMenu.Items.push(NotificationSystray);
    return NotificationSystray;
});
