# Generated manually for quota contacts + paiements MyPVit (Gabon).

import django.db.models.deletion
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nde", "0004_ownernotification_historicalownernotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="remoteuser",
            name="contact_subscription_until",
            field=models.DateTimeField(
                blank=True,
                help_text="Fin de validité du pass contacts (paiement via MyPVit Gabon).",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="HistoricalContactReveal",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("is_deleted", models.BooleanField(default=False)),
                (
                    "history_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("history_date", models.DateTimeField(db_index=True)),
                (
                    "history_change_reason",
                    models.CharField(max_length=100, null=True),
                ),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "maison",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="nde.maison",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical contact reveal",
                "verbose_name_plural": "historical contact reveals",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalContactAccessPayment",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("is_deleted", models.BooleanField(default=False)),
                ("amount_xaf", models.PositiveIntegerField()),
                (
                    "merchant_reference",
                    models.CharField(db_index=True, max_length=64),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("paid", "Payé"),
                            ("failed", "Échec"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("pvit_transaction_id", models.CharField(blank=True, max_length=191)),
                ("webhook_payload", models.JSONField(blank=True, null=True)),
                ("init_response", models.JSONField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "history_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("history_date", models.DateTimeField(db_index=True)),
                (
                    "history_change_reason",
                    models.CharField(max_length=100, null=True),
                ),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical contact access payment",
                "verbose_name_plural": "historical contact access payments",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="ContactReveal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                (
                    "maison",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contact_reveals",
                        to="nde.maison",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contact_reveals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ContactAccessPayment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("amount_xaf", models.PositiveIntegerField()),
                (
                    "merchant_reference",
                    models.CharField(max_length=64, unique=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("paid", "Payé"),
                            ("failed", "Échec"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("pvit_transaction_id", models.CharField(blank=True, max_length=191)),
                ("webhook_payload", models.JSONField(blank=True, null=True)),
                ("init_response", models.JSONField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contact_access_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="contactreveal",
            index=models.Index(fields=("user", "created_at"), name="nde_contact_user_id_bd7e8c_idx"),
        ),
        migrations.AddConstraint(
            model_name="contactreveal",
            constraint=models.UniqueConstraint(
                fields=("user", "maison"),
                name="unique_contact_reveal_user_maison",
            ),
        ),
    ]
