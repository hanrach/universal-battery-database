# Generated by Django 2.2.11 on 2020-07-23 18:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cell_database', '0004_auto_20200701_1500'),
    ]

    operations = [
        migrations.CreateModel(
            name='MyCache',
            fields=[
                ('name', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('cache', models.BinaryField(max_length=10485760, null=True)),
                ('write_time', models.DateTimeField()),
            ],
        ),
    ]