# Delta for admin-direct-client-creation

## ADDED Requirements

### Requirement: Single wizard entry with required origin

The admin-facing `/cms/clientes` page MUST expose a single client-creation entry point. The page MUST NOT render any standalone "Crear cliente directo" button. Activating the remaining entry MUST mount the same five-step wizard used for `prospect` and `reactivation` modes, in `mode='direct'`. Step 1 of that wizard MUST require the admin to select the `origen` value before the "Siguiente" (next) control becomes enabled. Selecting "Sí, ya fue paciente" sets `origen = RECURRENTE_PRE_SISTEMA`; selecting "No, es nuevo" sets `origen = NUEVO`.

#### Scenario: Admin opens the wizard from the single entry

- GIVEN an authenticated admin on `/cms/clientes`
- WHEN the admin activates the client-creation entry
- THEN the wizard opens at step 1 in `mode='direct'`
- AND step 1 displays the required `origen` radio at the top

#### Scenario: No standalone direct-creation button is rendered

- GIVEN an authenticated admin on `/cms/clientes`
- WHEN the page renders
- THEN no "Crear cliente directo" button or equivalent standalone entry is visible
- AND exactly one client-creation entry is shown

## REMOVED Requirements

### Requirement: Direct Client Entry Point

(Reason: the standalone "Crear cliente directo" button is removed. Client creation now flows through the unified wizard's `mode='direct'`, where the origin question lives inside step 1. Marking the whole spec for archive: the dedicated entry-point capability no longer exists as a distinct flow.)
(Migration: any UI test, screenshot, doc, or copy referencing "Crear cliente directo" MUST be updated to use the unified wizard's `mode='direct'` entry on `/cms/clientes`. The dedicated route still mounts the wizard, so deep links continue to work; only the labeled entry on the listing page changes.)

### Requirement: Step 1 Uniqueness

(Reason: uniqueness behavior for `ci` and `username` is unchanged, but the requirement was specific to the standalone direct-creation flow that is being removed. The same uniqueness invariants are preserved by the `admin-prospect-conversion` spec under the unified wizard's `mode='direct'` branch.)
(Migration: tests asserting uniqueness on direct-mode step 1 MUST be re-anchored to the `admin-prospect-conversion` spec under `mode='direct'`.)

### Requirement: Steps 2–5 Behavior

(Reason: the steps 2–5 behavior for direct creation is unchanged, but the requirement was anchored to the standalone direct-creation spec. The same invariants are preserved by `admin-prospect-conversion` Step 1 ReadOnly Behavior Per Mode + Finalize Dispatcher Per Mode + Common Step Validation Across Modes.)
(Migration: any test referencing direct-mode steps 2–5 in isolation MUST be re-anchored to the unified wizard's `mode='direct'` branch under `admin-prospect-conversion`.)

### Requirement: Finalize Atomic Creation

(Reason: atomic finalize for direct creation is preserved, but the requirement is now expressed through `admin-prospect-conversion`'s "Finalize Dispatcher Per Mode" requirement. The `direct` branch already creates `Usuario (CLIENTE)` + `Cliente` inside one transaction.)
(Migration: finalize-side atomic-creation assertions for direct mode MUST be re-anchored under `admin-prospect-conversion` › "Finalize Dispatcher Per Mode" › "Direct finalize" scenario.)

### Requirement: New Client Appears in Listing

(Reason: behavior is unchanged but is no longer owned by a standalone direct-creation flow. Listing semantics already live in the broader admin-client-listing capability outside this change.)
(Migration: tests that a newly finalized direct client appears in `/cms/clientes` MUST continue to assert the same outcome; only the owner spec changes.)

### Requirement: Cancel Cleans Up the Draft

(Reason: cancel semantics are unchanged and now live in `admin-prospect-conversion` › "Cancel Works Across All Modes".)
(Migration: cancel-cleanup tests for direct mode MUST be re-anchored under `admin-prospect-conversion` › "Cancel Works Across All Modes".)
