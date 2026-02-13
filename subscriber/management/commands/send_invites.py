from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

import config
from subscriber.models import EmailSubscriber

class Command(BaseCommand):
    help = "Send invite emails to subscribers"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **opts):
        limit = opts["limit"]

        qs = EmailSubscriber.objects.filter(
            invited_at__isnull=True,
        )[:limit]

        base_url = getattr(config, "BASE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("Set settings.BASE_URL, e.g. https://yourdomain.com")

        sent = 0
        for s in qs:
            invite_path = reverse("register_initial")
            invite_url = f"{base_url}{invite_path}"

            send_mail(
                subject="Ваше приглашение на регистрацию",
                message=(
                    "Привет!\n\n"
                    "Регистрация в программу 'Поддержи таланты' БФ 'Путёвка в жизнь' открыта. Вот ссылка:\n"
                    f"{invite_url}\n\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[s.email],
                fail_silently=False,
            )
            s.invited_at = timezone.now()
            s.save(update_fields=["invited_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent invites: {sent}"))
