# HR model classes — importing them here registers each via the metaclass and makes the
# installer migrate its table. dodoo emits no DB-level FKs, so import order is irrelevant.
# Grouped by user story: P1 Employees/Contracts/Skills, P2 Time Off, P3 Recruitment.

from dodoo.addons.hr.models.hr_applicant import HrApplicant
from dodoo.addons.hr.models.hr_applicant_refuse_reason import HrApplicantRefuseReason
from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
from dodoo.addons.hr.models.hr_appraisal_feedback import HrAppraisalFeedback
from dodoo.addons.hr.models.hr_appraisal_template import (
    HrAppraisalFeedbackSection,
    HrAppraisalTemplate,
)
from dodoo.addons.hr.models.hr_contract import HrContract
from dodoo.addons.hr.models.hr_contract_type import HrContractType
from dodoo.addons.hr.models.hr_department import HrDepartment
from dodoo.addons.hr.models.hr_employee import HrEmployee
from dodoo.addons.hr.models.hr_employee_category import HrEmployeeCategory
from dodoo.addons.hr.models.hr_job import HrJob
from dodoo.addons.hr.models.hr_leave import HrLeave
from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
from dodoo.addons.hr.models.hr_leave_type import HrLeaveType
from dodoo.addons.hr.models.hr_public_holiday import HrPublicHoliday
from dodoo.addons.hr.models.hr_recruitment_source import HrRecruitmentSource
from dodoo.addons.hr.models.hr_recruitment_stage import HrRecruitmentStage
from dodoo.addons.hr.models.hr_referral import HrReferral
from dodoo.addons.hr.models.hr_skill import (
    HrEmployeeSkill,
    HrSkill,
    HrSkillLevel,
    HrSkillType,
)
from dodoo.addons.hr.models.resource_calendar import (
    ResourceCalendar,
    ResourceCalendarAttendance,
)

__all__ = [
    "HrDepartment",
    "HrJob",
    "HrEmployee",
    "HrEmployeeCategory",
    "HrContractType",
    "HrContract",
    "HrSkillType",
    "HrSkill",
    "HrSkillLevel",
    "HrEmployeeSkill",
    "ResourceCalendar",
    "ResourceCalendarAttendance",
    "HrPublicHoliday",
    "HrLeaveType",
    "HrLeaveAllocation",
    "HrLeave",
    "HrRecruitmentStage",
    "HrRecruitmentSource",
    "HrApplicantRefuseReason",
    "HrApplicant",
    "HrAppraisalTemplate",
    "HrAppraisalFeedbackSection",
    "HrAppraisalFeedback",
    "HrAppraisal",
    "HrReferral",
]
