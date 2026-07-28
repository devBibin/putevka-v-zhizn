from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_documenttype_document_document_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="slot_label",
            field=models.CharField(
                blank=True,
                help_text="Например: разворот с фотографией или страница регистрации",
                max_length=100,
                verbose_name="Подпись файла в слоте",
            ),
        ),
    ]
