export const ACCOUNTING_MENU = [
  {
    section: 'Customers',
    items: [
      { label: 'Invoices',     hash: '#/accounting/invoices' },
      { label: 'Credit Notes', hash: '#/accounting/credit-notes' },
      { label: 'Payments',     hash: '#/accounting/customer-payments' },
    ],
  },
  {
    section: 'Vendors',
    items: [
      { label: 'Bills',        hash: '#/accounting/bills' },
      { label: 'Credit Notes', hash: '#/accounting/vendor-credit-notes' },
      { label: 'Payments',     hash: '#/accounting/vendor-payments' },
    ],
  },
  {
    section: 'Accounting',
    items: [
      { label: 'Journal Entries',   hash: '#/accounting/journal-entries' },
      { label: 'Chart of Accounts', hash: '#/accounting/chart-of-accounts' },
      { label: 'Journals',          hash: '#/accounting/journals' },
    ],
  },
  {
    section: 'Reporting',
    items: [
      { label: 'Trial Balance',   hash: '#/accounting/reports/trial-balance' },
      { label: 'General Ledger',  hash: '#/accounting/reports/general-ledger' },
      { label: 'Profit & Loss',   hash: '#/accounting/reports/profit-loss' },
      { label: 'Balance Sheet',   hash: '#/accounting/reports/balance-sheet' },
      { label: 'Aged Receivable', hash: '#/accounting/reports/aged-receivable' },
      { label: 'Aged Payable',    hash: '#/accounting/reports/aged-payable' },
    ],
  },
];
