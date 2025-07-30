from django.core.management.base import BaseCommand
from django.conf import settings
import telebot
import os

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('action', type=str, help='Действие: "set" для установки, "delete" для удаления, "info" для получения информации')
        parser.add_argument('--url', type=str, help='Базовый URL вашего домена (например, https://your-domain.com), обязателен для "set"')
        parser.add_argument('--token', type=str, default=os.getenv('TELEGRAM_BOT_TOKEN'), help='Токен вашего Telegram бота. По умолчанию берется из переменной окружения TELEGRAM_BOT_TOKEN.')

    def handle(self, *args, **options):
        action = options['action']
        base_url = options['url']
        bot_token = options['token']

        if not bot_token:
            self.stderr.write(self.style.ERROR("Токен бота не указан. Установите переменную окружения TG_TOKEN или используйте аргумент --token."))
            return

        bot = telebot.TeleBot(bot_token)

        if action == 'set':
            if not base_url:
                self.stderr.write(self.style.ERROR("Для установки вебхука необходимо указать --url."))
                return

            webhook_url = f"{base_url}/telegram/webhook/{bot_token}/"
            try:
                bot.set_webhook(url=webhook_url, drop_pending_updates=True)
                self.stdout.write(self.style.SUCCESS(f"Вебхук успешно установлен на: {webhook_url}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Ошибка при установке вебхука: {e}"))
        elif action == 'delete':
            try:
                bot.delete_webhook()
                self.stdout.write(self.style.SUCCESS("Вебхук успешно удален."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Ошибка при удалении вебхука: {e}"))
        elif action == 'info':
            try:
                webhook_info = bot.get_webhook_info()
                self.stdout.write(self.style.SUCCESS("Информация о вебхуке:"))
                self.stdout.write(f"  URL: {webhook_info.url if webhook_info.url else 'Не установлен'}")
                self.stdout.write(f"  Последняя ошибка: {webhook_info.last_error_message if webhook_info.last_error_message else 'Нет'}")
                self.stdout.write(f"  Время последней ошибки: {webhook_info.last_error_date if webhook_info.last_error_date else 'Нет'}")
                self.stdout.write(f"  Ожидающие обновления: {webhook_info.pending_update_count}")
                self.stdout.write(f"  Сертификат установлен: {webhook_info.has_custom_certificate}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Ошибка при получении информации о вебхуке: {e}"))
        else:
            self.stderr.write(self.style.ERROR("Неизвестное действие. Используйте 'set', 'delete' или 'info'."))