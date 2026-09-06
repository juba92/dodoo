# HR model classes — imported so the metaclass registers them and the installer migrates
# them. dodoo emits no DB-level FKs, so import order does not matter. Extended per user story.

# --- P1: Employees, org structure, tags, contracts, skills ---
from dodoo.addons.hr.models.hr_contract import HrContract
from dodoo.addons.hr.models.hr_contract_type import HrContractType
from dodoo.addons.hr.models.hr_department import HrDepartment
from dodoo.addons.hr.models.hr_employee import HrEmployee
from dodoo.addons.hr.models.hr_employee_category import HrEmployeeCategory
from dodoo.addons.hr.models.hr_job import HrJob

# --- P2: Time Off ---
from dodoo.addons.hr.models.hr_leave import HrLeave
from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
from dodoo.addons.hr.models.hr_leave_type import HrLeaveType
from dodoo.addons.hr.models.hr_public_holiday import HrPublicHoliday
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
    "HrEmployeeCategory",
    "HrDepartment",
    "HrJob",
    "HrEmployee",
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
]
