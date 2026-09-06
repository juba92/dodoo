// HR application menus (feature 006). Same shape as ACCOUNTING_MENU.
// `requires` gates the section client-side against /web/core/info (hr_groups / fleet_manager);
// the real enforcement is the ir.rule record rules + REST action group checks.
export const HR_MENU = [
  {
    section: 'Employees', requires: null,
    items: [
      { label: 'Employees',   hash: '#/hr/employees' },
      { label: 'Departments',  hash: '#/hr/model/hr.department' },
      { label: 'Job Positions', hash: '#/hr/model/hr.job' },
      { label: 'Contracts',    hash: '#/hr/contracts' },
      { label: 'Tags',         hash: '#/hr/model/hr.employee.category', requires: 'administrator' },
    ],
  },
  {
    section: 'Recruitment', requires: 'officer',
    items: [
      { label: 'Job Positions', hash: '#/hr/recruitment' },
      { label: 'Stages',        hash: '#/hr/model/hr.recruitment.stage', requires: 'administrator' },
      { label: 'Refusal Reasons', hash: '#/hr/model/hr.applicant.refuse.reason', requires: 'administrator' },
    ],
  },
  {
    section: 'Time Off', requires: null,
    items: [
      { label: 'Calendar',     hash: '#/hr/timeoff' },
      { label: 'Allocations',  hash: '#/hr/allocations' },
      { label: 'Leave Types',  hash: '#/hr/model/hr.leave.type', requires: 'administrator' },
      { label: 'Public Holidays', hash: '#/hr/model/hr.public.holiday', requires: 'administrator' },
    ],
  },
  {
    section: 'Appraisals', requires: 'officer',
    items: [
      { label: 'Appraisals',   hash: '#/hr/appraisals' },
      { label: 'Templates',    hash: '#/hr/model/hr.appraisal.template', requires: 'administrator' },
    ],
  },
  {
    section: 'Referrals', requires: null,
    items: [
      { label: 'Refer a Friend', hash: '#/hr/referral/new' },
      { label: 'My Referrals',   hash: '#/hr/referrals' },
    ],
  },
];
