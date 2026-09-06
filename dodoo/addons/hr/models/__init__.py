# HR model classes — imported in dependency order so the metaclass registers them and
# the installer migrates them. Extended per user story.

# --- P1: Employees, org structure, tags, contracts, skills ---
from dodoo.addons.hr.models.hr_contract import HrContract
from dodoo.addons.hr.models.hr_contract_type import HrContractType
from dodoo.addons.hr.models.hr_department import HrDepartment
from dodoo.addons.hr.models.hr_employee import HrEmployee
from dodoo.addons.hr.models.hr_employee_category import HrEmployeeCategory
from dodoo.addons.hr.models.hr_job import HrJob
from dodoo.addons.hr.models.hr_skill import (
    HrEmployeeSkill,
    HrSkill,
    HrSkillLevel,
    HrSkillType,
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
]
