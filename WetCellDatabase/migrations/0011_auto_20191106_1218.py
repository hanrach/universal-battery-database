# Generated by Django 2.2.6 on 2019-11-06 16:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('WetCellDatabase', '0010_auto_20191105_1846'),
    ]

    operations = [
        migrations.RenameField(
            model_name='drycell',
            old_name='cell_model',
            new_name='name',
        ),
    ]
