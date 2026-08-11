---
title: "Резервные копии PostgreSQL"
description: "Автоматические зашифрованные дампы production PostgreSQL на Яндекс Диск."
search:
  exclude: true
---

# Резервные копии PostgreSQL на Яндекс Диск

База остаётся на production-сервере. Скрипт создаёт архив `pg_dump` внутри Docker-контейнера `db`, проверяет его командой `pg_restore --list`, загружает на Яндекс Диск и удаляет файлы старше 30 дней.

## OAuth-настройка (рекомендуется)

Нативный backend rclone `yandex` использует OAuth API Яндекса вместо WebDAV. Он создан отдельными remote, поэтому старый WebDAV remote и уже загруженные файлы остаются нетронутыми.

1. На production запусти `sudo rclone config` и создай remote `yadisk_oauth` типа `yandex`. Оставь `client_id` и `client_secret` пустыми.
2. На вопрос о браузере на сервере выбери `n` (сервер headless). На своём компьютере запусти `rclone authorize "yandex"`, войди в Яндекс и разреши доступ. Вставь напечатанный этой командой токен в ожидающий `sudo rclone config` на сервере. Токен не отправляй в чат и не добавляй в репозиторий.
3. В том же `sudo rclone config` создай `yadisk_oauth_crypt` типа `crypt` с путём `yadisk_oauth:putevka-backups-oauth`. Для читаемых имён выбери `filename_encryption = off`; содержимое при этом остаётся зашифрованным. Пароль crypt сохрани в менеджере паролей.
4. Проверь доступ: `sudo rclone lsd yadisk_oauth:` и измени в `/etc/putevka-backup.env` значение на `RCLONE_REMOTE=yadisk_oauth_crypt`.

## WebDAV-настройка (старый вариант)

1. В Яндекс ID создай пароль приложения типа **WebDAV-клиент для Яндекс Диска**. Не используй основной пароль аккаунта.
2. На production установи rclone и выполни `sudo rclone config`.
3. Создай remote `yadisk`: тип `webdav`, URL `https://webdav.yandex.ru`, vendor `other`, логин Яндекс ID и пароль приложения.
4. Создай remote `yadisk_crypt`: тип `crypt`, путь `yadisk:putevka-backups`; включи шифрование имён и содержимого. Пароль crypt сохрани в менеджере паролей.
5. Проверь доступ: `sudo rclone lsd yadisk:`.

## Установка на production

После однократной настройки rclone установка timer выполняется через GitHub Actions: **Actions → Configure Production Backups → Run workflow**. Если `/etc/putevka-backup.env` ещё нет, workflow создаст его с путём текущего production-репозитория, ежедневной ротацией 30 дней и remote `yadisk_crypt`. Для OAuth нужно один раз заменить remote в этом файле на `yadisk_oauth_crypt`; workflow проверяет именно указанный в файле remote.

Workflow использует существующий production SSH-доступ и требует, чтобы deploy-пользователь мог выполнить `sudo` без запроса пароля. Пароль Яндекс Диска и пароль шифрования rclone остаются только на production-сервере.

Если GitHub Actions пока не используется, можно выполнить ту же установку вручную:

```bash
cd /srv/putevka-v-zhizn
sudo install -m 0750 scripts/backup-postgres-to-yadisk.sh /usr/local/sbin/putevka-postgres-backup
sudo install -m 0600 deploy/backups/putevka-backup.env.example /etc/putevka-backup.env
sudoedit /etc/putevka-backup.env
sudo install -m 0644 deploy/backups/putevka-postgres-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/backups/putevka-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now putevka-postgres-backup.timer
sudo systemctl start putevka-postgres-backup.service
sudo journalctl -u putevka-postgres-backup.service -n 100 --no-pager
```

В `/etc/putevka-backup.env` укажи настоящий `APP_DIR` и один из crypt remote: `yadisk_oauth_crypt` для OAuth либо `yadisk_crypt` для WebDAV. Нативный remote без суффикса `_crypt` не шифрует дампы. Timer запускает задачу ежедневно в 03:30 UTC (10:30 по Томску при UTC+7) и наверстывает запуск после перезагрузки. Один запуск ограничен 30 минутами, а rclone выводит прогресс в журнал раз в 30 секунд.

Раз в квартал скачивай один архив в отдельную папку и проверяй `sha256sum -c *.sha256` и `pg_restore --list`; не восстанавливай тестовый файл поверх production.
