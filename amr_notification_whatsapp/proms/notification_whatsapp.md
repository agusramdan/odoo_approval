Buat modul Odoo 13 bernama `amr_notification_whatsapp` di `../`.

Spesifikasi:

Inheit Model `notification.partner`:
- `name` (Char)
- `send_whatsapp` (Boolean` flag send notification)

Tambahkan Model `notification.whatsapp` sebagai log delivery ke whatsap serupa dengan model notification.delivery

Views & menu:
- Form view + tree view untuk `notification.partner`
- Menu item dan action `ir.actions.act_window`

Security:
- Tambahkan `security/ir.model.access.csv` untuk akses user

Manifest:
- Buat `__manifest__.py` dengan urutan: `name`, `version`, `category`, `summary`, `description`, `author`, `website`, `license`, `depends`, `data`, `demo`, `assets`, `installable`, `auto_install`, `application`, `externaldepenency`


Implementasi whatsapp api https://developers.facebook.com/documentation/business-messaging/messenger-platform/send-messages

buatkan tests case untuk addons ini.