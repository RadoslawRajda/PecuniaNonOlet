"""Provision currency accounts and opening balances for existing users."""

from alembic import op

revision = "0003_initial_balances"
down_revision = "0002_user_roles"
branch_labels = None
depends_on = None

CURRENCIES = ("PLN", "EUR", "USD", "GBP", "CZK")
INITIAL_PLN_MINOR = 100_000
IDEMPOTENCY_KEY = "opening-balance-pln-v1"


def upgrade() -> None:
    connection = op.get_bind()
    users = connection.exec_driver_sql("SELECT id, created_at FROM users ORDER BY id").fetchall()
    for user_id, created_at in users:
        for currency in CURRENCIES:
            connection.exec_driver_sql(
                "INSERT OR IGNORE INTO accounts(user_id, currency_code, balance_minor) VALUES (?, ?, 0)",
                (user_id, currency),
            )

        already_granted = connection.exec_driver_sql(
            "SELECT id FROM transactions WHERE sender_user_id = ? AND idempotency_key = ?",
            (user_id, IDEMPOTENCY_KEY),
        ).first()
        if already_granted is not None:
            continue

        account = connection.exec_driver_sql(
            "SELECT id FROM accounts WHERE user_id = ? AND currency_code = 'PLN'",
            (user_id,),
        ).first()
        if account is None:
            raise RuntimeError("PLN account provisioning failed")
        account_id = account[0]
        connection.exec_driver_sql(
            "UPDATE accounts SET balance_minor = balance_minor + ? WHERE id = ?",
            (INITIAL_PLN_MINOR, account_id),
        )
        transaction_id = f"init-pln-{user_id}"
        connection.exec_driver_sql(
            """
            INSERT INTO transactions(
                id, kind, status, sender_user_id, recipient_user_id,
                source_account_id, source_account_user_id,
                destination_account_id, destination_account_user_id,
                source_currency_code, destination_currency_code,
                source_amount_minor, destination_amount_minor,
                exchange_rate, provider, idempotency_key, created_at
            ) VALUES (?, 'opening', 'completed', ?, NULL, NULL, NULL, ?, ?, NULL, 'PLN',
                      NULL, ?, NULL, NULL, ?, ?)
            """,
            (
                transaction_id,
                user_id,
                account_id,
                user_id,
                INITIAL_PLN_MINOR,
                IDEMPOTENCY_KEY,
                created_at,
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO ledger_entries(
                transaction_id, account_id, account_user_id, amount_minor, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (transaction_id, account_id, user_id, INITIAL_PLN_MINOR, created_at),
        )


def downgrade() -> None:
    raise RuntimeError("Initial balance migration is forward-only to preserve financial records.")
