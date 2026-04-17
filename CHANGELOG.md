# Changelog

## [Unreleased] - 2026-04-14

### Added
- `devices/balance_fake_interface.py`: `BalanceFakeInterface` — fake implementation of `BalanceInterface` for testing without hardware
- `devices/high_viscosity_dispenser_fake_interface.py`: `HighViscosityDispenserFakeInterface` — fake implementation of `HighViscosityDispenserInterface` for testing without hardware
- Both fake classes registered in `DEVICE_REGISTRY`; switch via `_class:` in `devices.settings.yaml`
- `interface_type: fake` global default added to `node.settings.yaml`; per-device override via `_interface_type:` in `devices.settings.yaml`
- `DEVICE_INTERFACE_TYPE_OVERRIDES` ClassVar and `interface_type` field added to `HighViscosityLiquidWeighingConfig`
- `startup_handler` now resolves real vs fake class per device based on `interface_type` and per-device `_interface_type` override

### Changed
- `Balance` → `BalanceInterface`、`balance.py` → `balance_interface.py` にリネーム
- `HighViscosityDispenser` → `HighViscosityDispenserInterface`、`high_viscosity_dispenser.py` → `high_viscosity_dispenser_interface.py` にリネーム
- `devices/__init__.py`、`devices.settings.yaml`、`modules/high_viscosity_liquid_weighing.py` の参照を新クラス名に更新

## [Unreleased] - 2026-04-13

### Changed
- `HighViscosityDispenser`: Added `full_steps_per_rev`, `microstep_multiplier`, `purge_speed_rps` parameters to `__init__`
- `HighViscosityDispenser`: Added `motion_status` attribute (`"idle"` / `"dispensing"` / `"purging"`)
- `HighViscosityDispenser`: Added public methods `dispense(rotations, speed_rps)`, `suck_back(rotations, speed_rps)`, `purge(rotations)`
- `HighViscosityDispenser`: Added private helpers `_set_max_speed`, `_rotations_to_microsteps`
- `HighViscosityDispenser`: `close()` now calls `_halt_and_hold()` before deenergizing
