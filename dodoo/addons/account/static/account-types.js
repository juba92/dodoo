/**
 * Account-type metadata shared by the Chart of Accounts list and the account form.
 * Labels mirror ACCOUNT_TYPE_CHOICES in account_account.py exactly so they double as
 * translation-catalog keys; `group` is Odoo's internal group used by the CoA filters.
 */

export const ACCOUNT_TYPES = {
  asset_receivable:      { label: 'Receivable',              group: 'asset' },
  asset_cash:            { label: 'Bank and Cash',           group: 'asset' },
  asset_current:         { label: 'Current Assets',          group: 'asset' },
  asset_non_current:     { label: 'Non-current Assets',      group: 'asset' },
  asset_prepayments:     { label: 'Prepayments',             group: 'asset' },
  asset_fixed:           { label: 'Fixed Assets',            group: 'asset' },
  liability_payable:     { label: 'Payable',                 group: 'liability' },
  liability_credit_card: { label: 'Credit Card',             group: 'liability' },
  liability_current:     { label: 'Current Liabilities',     group: 'liability' },
  liability_non_current: { label: 'Non-current Liabilities', group: 'liability' },
  equity:                { label: 'Equity',                  group: 'equity' },
  equity_unaffected:     { label: 'Current Year Earnings',   group: 'equity' },
  income:                { label: 'Income',                  group: 'income' },
  income_other:          { label: 'Other Income',            group: 'income' },
  expense:               { label: 'Expenses',                group: 'expense' },
  expense_other:         { label: 'Other Expenses',          group: 'expense' },
  expense_depreciation:  { label: 'Depreciation',            group: 'expense' },
  expense_direct_cost:   { label: 'Cost of Revenue',         group: 'expense' },
  off_balance:           { label: 'Off Balance',             group: 'off_balance' },
};

/** Stable display order for the Type <select> and the grouped list. */
export const ACCOUNT_TYPE_ORDER = Object.keys(ACCOUNT_TYPES);

/** AR/AP accounts must stay reconcilable — matches account_account.py guards. */
export const RECONCILABLE_TYPES = new Set(['asset_receivable', 'liability_payable']);

export function typeLabel(code) {
  return ACCOUNT_TYPES[code] ? ACCOUNT_TYPES[code].label : (code || '');
}

export function typeGroup(code) {
  return ACCOUNT_TYPES[code] ? ACCOUNT_TYPES[code].group : '';
}
