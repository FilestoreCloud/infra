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
    "runuser -u www-data -- php /var/www/html/occ maintenance:install "
    "--database pgsql "
    "--database-host \"$POSTGRES_HOST\" "
    "--database-name \"$POSTGRES_DB\" "
    "--database-user \"$POSTGRES_USER\" "
    "--database-pass \"$POSTGRES_PASSWORD\" "
    "--admin-user \"$NEXTCLOUD_ADMIN_USER\" "
    "--admin-pass \"$NEXTCLOUD_ADMIN_PASSWORD\" "
    "--data-dir /var/www/html/data\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 0 --value=localhost\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 1 --value=127.0.0.1\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 2 --value=dev-tenant.png261.dev\n"
    "runuser -u www-data -- php /var/www/html/occ config:system:set trusted_domains 3 --value=\"*.png261.dev\"\n"
    "rm -f /var/www/html/config/CAN_INSTALL 2>/dev/null || :\n"
    "chown -R www-data:www-data /var/www/html/config 2>/dev/null || :\n"
    "echo NEXTCLOUD_INSTALLED_SUCCESSFULLY"
]

payload = {"containerOverrides": [{"name": "nextcloud", "command": cmd}]}
with open("overrides.json", "w") as f:
    json.dump(payload, f, indent=2)
print("Generated overrides.json successfully.")
