"""Mock bank tools for the local remote agent.

In a real deployment these tools would query the bank's internal systems
(core banking, card processor, CRM). Here they return fixed, in-memory data so
the demo is deterministic and offline: the local agent does NOT invent balances
with the LLM — it looks them up through a tool, which is how it would work in
production.

The tools are exposed to the Strands `Agent` via the `@tool` decorator; the
model decides which one to call based on their descriptions.
"""

from strands import tool

from common.logging_config import setup_logging

logger = setup_logging("remote_agent.log", "remote_agent")

# ─────────────────────────────────────────────────────────────────────────────
# In-memory "database" — fixed sample data keyed by account number.
# ─────────────────────────────────────────────────────────────────────────────
_ACCOUNTS: dict[str, dict] = {
    "1234-5678-9": {
        "holder": "Laura Bolaños",
        "account_type": "Caja de ahorro en pesos",
        "balance": "$1.480.750,25",
        "currency": "ARS",
        "last_transactions": [
            "2026-08-25  Transferencia recibida        +$320.000,00",
            "2026-08-24  Débito automático - Edenor      -$18.430,50",
            "2026-08-22  Compra con débito - Coto        -$45.900,00",
        ],
    },
    "9876-5432-1": {
        "holder": "Martín Quiroga",
        "account_type": "Cuenta corriente en pesos",
        "balance": "$92.310,00",
        "currency": "ARS",
        "last_transactions": [
            "2026-08-26  Pago de servicios - Metrogas     -$12.100,00",
            "2026-08-20  Depósito en efectivo           +$150.000,00",
        ],
    },
}

_ACCOUNT_NOT_FOUND = "No se encontró una cuenta con ese número en el sistema."


@tool
def get_account_balance(account_number: str) -> str:
    """Return the current balance of a bank account.

    Args:
        account_number: the account number, e.g. "1234-5678-9".

    Returns:
        A human-readable line with the holder and the current balance, or a
        not-found message if the account does not exist.
    """
    logger.info("TOOL CALL: get_account_balance(account_number=%r)", account_number)
    account = _ACCOUNTS.get(account_number.strip())
    if account is None:
        return _ACCOUNT_NOT_FOUND
    return (
        f"Cuenta {account_number} — Titular: {account['holder']}. "
        f"Saldo actual: {account['balance']} ({account['account_type']})."
    )


@tool
def get_last_transactions(account_number: str) -> str:
    """Return the most recent transactions of a bank account.

    Args:
        account_number: the account number, e.g. "1234-5678-9".

    Returns:
        A newline-separated list of recent transactions, or a not-found message.
    """
    logger.info("TOOL CALL: get_last_transactions(account_number=%r)", account_number)
    account = _ACCOUNTS.get(account_number.strip())
    if account is None:
        return _ACCOUNT_NOT_FOUND
    lines = "\n".join(account["last_transactions"])
    return f"Últimos movimientos de la cuenta {account_number}:\n{lines}"


@tool
def get_account_holder(account_number: str) -> str:
    """Return the account holder's name and account type.

    Args:
        account_number: the account number, e.g. "1234-5678-9".

    Returns:
        The holder's name and account type, or a not-found message.
    """
    logger.info("TOOL CALL: get_account_holder(account_number=%r)", account_number)
    account = _ACCOUNTS.get(account_number.strip())
    if account is None:
        return _ACCOUNT_NOT_FOUND
    return (
        f"La cuenta {account_number} pertenece a {account['holder']} "
        f"({account['account_type']})."
    )
