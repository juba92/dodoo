// Fleet application menu (feature 006). `requires: 'fleet_manager'` gated client-side.
export const FLEET_MENU = [
  {
    section: 'Fleet', requires: null,
    items: [
      { label: 'Vehicles', hash: '#/fleet/vehicles' },
      { label: 'Alerts',   hash: '#/fleet/alerts' },
    ],
  },
  {
    section: 'Configuration', requires: 'fleet_manager',
    items: [
      { label: 'Brands', hash: '#/fleet/model/fleet.vehicle.model.brand' },
      { label: 'Models', hash: '#/fleet/model/fleet.vehicle.model' },
    ],
  },
];
