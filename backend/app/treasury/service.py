"""Fungsi treasury dipakai lintas modul (saldo, catat mutasi, bayar dari rekening)."""
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from .models import AccountTransaction, BankAccount


def account_balance(account_id) -> float:
    acc = db.session.get(BankAccount, account_id)
    if not acc:
        return 0.0
    ins = db.session.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter_by(account_id=account_id, direction="in").scalar() or 0
    outs = db.session.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter_by(account_id=account_id, direction="out").scalar() or 0
    return round(float(acc.opening_balance or 0) + float(ins) - float(outs), 2)


def account_balance_asof(account_id, as_of_date) -> float:
    """Saldo sistem per tanggal tertentu (utk rekonsiliasi bank vs rekening koran)."""
    acc = db.session.get(BankAccount, account_id)
    if not acc:
        return 0.0
    ins = db.session.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter(
        AccountTransaction.account_id == account_id, AccountTransaction.direction == "in",
        AccountTransaction.tx_date <= as_of_date,
    ).scalar() or 0
    outs = db.session.query(func.coalesce(func.sum(AccountTransaction.amount), 0)).filter(
        AccountTransaction.account_id == account_id, AccountTransaction.direction == "out",
        AccountTransaction.tx_date <= as_of_date,
    ).scalar() or 0
    return round(float(acc.opening_balance or 0) + float(ins) - float(outs), 2)


def record_tx(account_id, direction, amount, kind, ref_type=None, ref_id=None, note=None, user_id=None, tx_date=None):
    tx = AccountTransaction(
        account_id=account_id, direction=direction, amount=Decimal(str(amount)),
        kind=kind, ref_type=ref_type, ref_id=ref_id, note=note, created_by=user_id,
    )
    if tx_date:
        tx.tx_date = tx_date
    db.session.add(tx)
    return tx


def holding_account():
    return BankAccount.query.filter_by(type="holding", is_active=True).first()


def venue_account(venue_id):
    return BankAccount.query.filter_by(type="venue", venue_id=venue_id, is_active=True).first()


def pay_expense(source_account_id, amount, ref_type, ref_id, note, user_id):
    """Catat pengeluaran keluar dari rekening sumber. Return (ok, error_msg)."""
    if not source_account_id:
        return False, "Sumber dana (rekening) wajib dipilih"
    acc = db.session.get(BankAccount, source_account_id)
    if not acc:
        return False, "Rekening tidak ditemukan"
    record_tx(source_account_id, "out", amount, "expense", ref_type, ref_id, note, user_id)
    return True, None
