# Contract: Fleet (`dodoo/addons/fleet/`)

`fleet` depends on `hr` (driver link only). REST routes mounted under `/fleet/…`; static under
`/fleet/static`. All mutation routes `auth="session"`; write access = `Fleet Manager` group;
`HR Officer` has read; a driver may read their own vehicle(s).

## JSON-RPC (`execute_kw`)

| Model | Method | Args / kwargs | Returns | Notes |
|-------|--------|---------------|---------|-------|
| fleet.vehicle.model.brand | create/write/read/search | standard | | global; Fleet Manager write |
| fleet.vehicle.model | create/write/read/search | standard | | `brand_id` required |
| fleet.vehicle | create/write/read/search/search_read | standard | `brand_id` derived from `model_id`; `odometer` = latest log value | `uid` → driver-reads-own rule |
| fleet.vehicle | `get_assigned` | kwargs `{employee_id:int}` | `[{id, name, state}]` | vehicles where `driver_id = employee_id` (FR-054) |
| fleet.vehicle.odometer | create/read/search | standard | | `inconsistent` set on create if `value < max` |
| fleet.vehicle.log.contract | create/write/read/search | standard | | `expiration_date >= start_date` |
| fleet.vehicle.log.contract | `get_expiry_alerts` | kwargs `{window_days:int|null}` | `[{contract_id, vehicle_id, vehicle_name, cost_type, expiration_date, days_left}]` | FR-056; default window 30; PERF-004 |
| fleet.vehicle.log.services | create/write/read/search | standard | | service history |

## REST routes

### `POST /fleet/vehicle/{vehicle_id}/set-state`
Body: `{ "state": "new_request|to_order|ordered|registered|downgraded|reserved|waiting_list",
         "expected_state": "<state>|null" }`.
- AuthZ: `Fleet Manager`.
- Stale → `vehicle_state_conflict` (FR-067a).
- Success: `{ "result": { "id": vehicle_id, "state": "<new>" } }`. Logs `fleet_vehicle_state`.

### `POST /fleet/vehicle/{vehicle_id}/assign-driver`
Body: `{ "driver_id": int|null }`.
- Appends the prior `driver_id` to `former_driver_ids`. `null` clears the driver.
- Success: `{ "result": { "id": vehicle_id, "driver_id": int|null } }`. Logs `fleet_driver_assign`.

### `GET /fleet/alerts`
Query: `?window_days=<int>` (optional). AuthZ: `Fleet Manager` or `HR Officer`.
Returns the `get_expiry_alerts` payload.

### `POST /fleet/cron/contract-expiry`
Body: `{}`. AuthZ: `Fleet Manager`. Idempotent — flips `open` contracts with
`expiration_date < today` to `expired`. Returns `{ "result": { "expired": <count> } }`.

## Validation models (fleet/validators.py)

```
BrandCreate:     name:str(1..64)
ModelCreate:     name:str(1..64); brand_id:int
VehicleCreate:   model_id:int; license_plate:str(0..32)|None; company_id:int;
                 state:Literal[<7 values>]='new_request'; driver_id:int|None
VehicleSetState: state:Literal[<7 values>]; expected_state:Literal[<7 values>]|None
AssignDriver:    driver_id:int|None
OdometerCreate:  vehicle_id:int; value:float(ge=0); date:date
ContractLogCreate: vehicle_id:int; cost_type:Literal['leasing','insurance']; amount:Decimal(ge=0)=0;
                   start_date:date; expiration_date:date
                   @model_validator: expiration_date >= start_date
ServiceLogCreate: vehicle_id:int; service_type:str(1..64); date:date; amount:Decimal(ge=0)=0;
                  notes:str|None
```

## Error codes
`vehicle_state_conflict`, `fleet_not_authorized`, `fleet_contract_dates`, `fleet_brand_model_mismatch`.
