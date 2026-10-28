#!/usr/bin/env python3
import json

php_code = (
    'try { '
    '$pdo = new PDO("pgsql:host=" . getenv("POSTGRES_HOST") . ";dbname=" . getenv("POSTGRES_DB"), getenv("POSTGRES_USER"), getenv("POSTGRES_PASSWORD"), [PDO::ATTR_TIMEOUT => 10]); '
    '$u = getenv("POSTGRES_USER"); '
    '$pdo->exec("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO \\"$u\\"; GRANT ALL ON SCHEMA public TO public;"); '
    'echo "DB_CLEANED_SUCCESS\\n"; '
    '} catch (Exception $e) { '
    'echo "DB_CLEAN_ERR: " . $e->getMessage() . "\\n"; exit(1); '
    '}'
)

cmd = [
    "sh", "-c",
    "set -e\n"
    "rm -f /var/www/html/config/config.php /var/www/html/config/CAN_INSTALL\n"
    f"php -r '{php_code}'\n"
    "cp -p /usr/src/nextcloud/version.php /var/www/html/version.php\n"
    "mkdir -p /var/www/html/config /var/www/html/data\n"
    "chown -R www-data:www-data /var/www/html/config /var/www/html/data 2>/dev/null || :\n"
    "chmod -R 775 /var/www/html/config 2>/dev/null || :\n"
    "ADMIN_PWD=\"${NEXTCLOUD_ADMIN_PASSWORD:-StorixAdmin2026!Secure}\"\n"
    "runuser -u www-data -- php /var/www/html/occ maintenance:install "
    "--database pgsql "
    "--database-host \"$POSTGRES_HOST\" "
    "--database-name \"$POSTGRES_DB\" "
    "--database-user \"$POSTGRES_USER\" "
    "--database-pass \"$POSTGRES_PASSWORD\" "
    "--admin-user \"$NEXTCLOUD_ADMIN_USER\" "
    "--admin-pass \"$ADMIN_PWD\" "
    "--data-dir /var/www/html/data 2>&1 || :\n"
    "runuser -u www-data -- env OC_PASS=\"$ADMIN_PWD\" php /var/www/html/occ user:resetpassword --password-from-env admin 2>/dev/null || :\n"
    "runuser -u www-data -- env OC_PASS=\"$ADMIN_PWD\" php /var/www/html/occ user:add --password-from-env --display-name=\"Administrator\" admin 2>/dev/null || :\n"
    "runuser -u www-data -- env OC_PASS=\"$ADMIN_PWD\" php /var/www/html/occ user:resetpassword --password-from-env admin 2>/dev/null || :\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 0 --value=localhost\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 1 --value=127.0.0.1\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 2 --value=dev-tenant.png261.dev\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 3 --value=\"*.png261.dev\"\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 4 --value=\"*.elb.amazonaws.com\"\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 5 --value=\"*\"\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set auth.bruteforce.protection.enabled --type=boolean --value=false\n"
    "sed -i 's/\\x27dbpassword\\x27/\"dbpassword\"/g' /var/www/html/config/config.php\n"
    "mkdir -p /var/www/html/data/admin/files\n"
    "echo \"Tai lieu mat he thong Storix ma khoa DOC_QUYEN_NOI_DUNG_9999 bao mat doanh nghiep.\" > /var/www/html/data/admin/files/tai_lieu_bao_mat_storix.txt\n"
    "chown -R www-data:www-data /var/www/html/data 2>/dev/null || :\n"
    "runuser -u www-data -- php /var/www/html/occ files:scan admin 2>/dev/null || :\n"
    "rm -f /var/www/html/config/CAN_INSTALL 2>/dev/null || :\n"
    "chown -R www-data:www-data /var/www/html/config 2>/dev/null || :\n"
    "echo NEXTCLOUD_INSTALLED_SUCCESSFULLY"
]

payload = {"containerOverrides": [{"name": "nextcloud", "command": cmd}]}
with open("overrides.json", "w") as f:
    json.dump(payload, f, indent=2)
print("Generated overrides.json successfully.")
