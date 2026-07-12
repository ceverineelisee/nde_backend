from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nde", "0005_contact_access_pv_contactreveal_contactaccesspayment"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contactaccesspayment",
            old_name="pvit_transaction_id",
            new_name="kpay_transaction_id",
        ),
        migrations.RenameField(
            model_name="historicalcontactaccesspayment",
            old_name="pvit_transaction_id",
            new_name="kpay_transaction_id",
        ),
        migrations.AlterField(
            model_name="remoteuser",
            name="contact_subscription_until",
            field=models.DateTimeField(
                blank=True,
                help_text="Fin de validité du pass contacts (paiement via KPay).",
                null=True,
            ),
        ),
    ]
