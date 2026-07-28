from django.db import migrations, models
import django.db.models.deletion


def create_default_document_types(apps, schema_editor):
    DocumentType = apps.get_model("documents", "DocumentType")
    for order, name in enumerate(("Паспорт", "СНИЛС", "ИНН"), start=1):
        DocumentType.objects.get_or_create(
            name=name,
            defaults={"sort_order": order * 10, "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_document_yandex_disk_error_document_yandex_disk_path_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Пояснение для пользователя")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок отображения")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
            ],
            options={
                "verbose_name": "Тип документа",
                "verbose_name_plural": "Типы документов",
                "ordering": ("sort_order", "name", "pk"),
            },
        ),
        migrations.AddField(
            model_name="document",
            name="document_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="documents",
                to="documents.documenttype",
                verbose_name="Тип документа",
            ),
        ),
        migrations.RunPython(create_default_document_types, migrations.RunPython.noop),
    ]
