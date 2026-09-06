# Fleet model classes — importing registers each via the metaclass; the installer migrates.

from dodoo.addons.fleet.models.fleet_vehicle import FleetVehicle
from dodoo.addons.fleet.models.fleet_vehicle_log_contract import FleetVehicleLogContract
from dodoo.addons.fleet.models.fleet_vehicle_log_services import FleetVehicleLogServices
from dodoo.addons.fleet.models.fleet_vehicle_model import (
    FleetVehicleModel,
    FleetVehicleModelBrand,
)
from dodoo.addons.fleet.models.fleet_vehicle_odometer import FleetVehicleOdometer

__all__ = [
    "FleetVehicleModelBrand",
    "FleetVehicleModel",
    "FleetVehicle",
    "FleetVehicleOdometer",
    "FleetVehicleLogContract",
    "FleetVehicleLogServices",
]
