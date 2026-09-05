# Feature Specification: Localization & Settings

**Feature Branch**: `005-localization-settings`

**Created**: 2026-09-05

**Status**: Draft

**Input**: User description: "Add a Localization & Settings capability to dodoo so an administrator can configure the system language and the company country, and so that choosing a country automatically applies that country's currency and tax configuration."

## Clarifications

### Session 2026-09-05

- Q: Where is the system default language stored? → A: A `lang` field on the single `res.company` record; it is the fallback in effective-language resolution.
- Q: How does translated text reach the web UI? → A: The server resolves the effective language per request and returns translated model field labels, model names, and menu labels inside existing metadata/RPC responses; a separate read-only endpoint returns the static client-string catalog (buttons, validation/system messages) that the SPA loads once at bootstrap.
- Q: How is the translation catalog stored? → A: Static per-language JSON catalog files shipped in the localization addon and loaded into memory at startup; no database translation model and no in-app translation-editing UI.
- Q: What is the "neutral" country with no localization package? → A: United Kingdom (ISO `GB`), seeded as a normal country with default currency GBP and no localization package; selecting it applies no taxes, fiscal positions, tax label, or forced currency change.
- Q: How is a concurrent (stale) Settings save handled? → A: Optimistic concurrency — the save carries the company record's last write timestamp; if it no longer matches, the save is rejected and the administrator is told to reload and retry.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure system language and get a localized, direction-aware UI (Priority: P1)

An administrator opens the Settings screen and sets the system default language. Every user who has
not chosen a personal language immediately sees the entire application — menus, field labels,
buttons, and system/validation messages — rendered in that language. When the language is Arabic the
whole web UI is laid out right-to-left (text direction, alignment, and mirrored navigation); when it
is English it is laid out left-to-right. Numbers, dates, and monetary amounts follow the active
language's locale conventions.

**Why this priority**: This is the core of the capability and the minimum viable product. Without a
working translation layer and direction-aware layout there is no localization feature. It delivers
standalone value: an Arabic-first product usable by the target market on a fresh install.

**Independent Test**: On a fresh install (Arabic default), confirm every visible static string on the
login, home, list, and form screens renders in Arabic with a right-to-left layout. Change the system
language to English in Settings, reload, and confirm the same screens render in English left-to-right
with locale-correct dates and amounts.

**Acceptance Scenarios**:

1. **Given** a fresh install with no per-user language preferences, **When** a user loads any screen,
   **Then** all static UI strings render in Arabic and the layout is right-to-left.
2. **Given** an administrator on the Settings screen, **When** they change the system default language
   to English and save, **Then** on the next page load all users without a personal preference see the
   UI in English with a left-to-right layout.
3. **Given** the active language is Arabic, **When** a screen displays a date and a monetary amount,
   **Then** both are formatted using Arabic locale conventions (separators, date order, currency
   symbol placement) and digit order within numbers is preserved.
4. **Given** a UI string has no Arabic translation, **When** it is displayed with Arabic active,
   **Then** the English source string is shown instead of a blank label.

---

### User Story 2 - Personal language preference override (Priority: P2)

An individual user sets a personal language preference from their own profile/preferences. From then
on, every screen that user sees renders in their chosen language and direction, regardless of the
system default, and without affecting any other user.

**Why this priority**: Mixed-language teams are common; a personal override is expected behaviour but
the product is still usable without it (everyone falls back to the system default). It builds
directly on the P1 translation layer.

**Independent Test**: With the system default set to Arabic, have one user set their personal
language to English. Confirm that user sees English left-to-right on every screen while a second user
with no preference still sees Arabic right-to-left in the same session window.

**Acceptance Scenarios**:

1. **Given** the system default is Arabic and a user has set their personal language to English,
   **When** that user loads any screen, **Then** it renders in English left-to-right.
2. **Given** two users with different effective languages, **When** both use the system concurrently,
   **Then** each sees only their own effective language with no cross-contamination.
3. **Given** a newly created user with no personal language set, **When** they first log in,
   **Then** their effective language is the current system default.
4. **Given** a user whose personal language preference is later cleared, **When** they load a screen,
   **Then** their effective language reverts to the system default.

---

### User Story 3 - Select a company country and auto-apply its localization package (Priority: P2)

An administrator selects the company's country in Settings. Choosing a country with a localization
package (Egypt) automatically applies that package: the company's functional currency is set to the
country's currency (seeding the currency if needed), the country's sales and purchase taxes are
created at the correct rates and mapped to the right tax accounts, domestic and export fiscal
positions are created, and country-required document settings are applied (tax label, rounding
method, and the default taxes used on new products). The new taxes and fiscal position become the
active company defaults.

**Why this priority**: This is the "choosing a country configures currency and tax" promise of the
feature. It depends on the accounting module but not on the language work, so it can ship
independently after P1.

**Independent Test**: On a company set to the neutral country, select Egypt in Settings and save.
Confirm EGP is the functional currency, the four Egypt taxes and the two fiscal positions exist and
are set as defaults, and the document tax label reads "VAT".

**Acceptance Scenarios**:

1. **Given** a company set to the neutral country, **When** the administrator selects Egypt and saves,
   **Then** the functional currency becomes EGP (created if absent), the Egypt taxes and fiscal
   positions are created, and they are set as the active defaults.
2. **Given** Egypt has just been applied, **When** a user creates a new product, **Then** the product
   is pre-filled with the Egypt default sale tax (VAT 14%) and default purchase tax (VAT 14%).
3. **Given** Egypt is the selected country, **When** a document that shows tax is rendered, **Then**
   the tax label displayed is "VAT" and tax amounts use the round-globally method.
4. **Given** Egypt is already the selected country, **When** the administrator re-selects Egypt and
   saves, **Then** no duplicate currency, tax, or fiscal-position records are created.
5. **Given** a fresh install, **When** setup completes, **Then** the company country is Egypt and the
   full Egypt package (EGP + taxes + fiscal positions + defaults) is already applied with no manual
   steps.

---

### User Story 4 - Change the company country safely after accounting data exists (Priority: P3)

An administrator changes the company country after taxes, fiscal positions, and posted accounting
entries already exist. The system adds the new country's configuration alongside the existing one and
switches only the active defaults; it never deletes or alters posted data. If the change would
switch the company's functional currency while posted entries exist, the administrator is warned and
must explicitly confirm; declining aborts the change with no side effects.

**Why this priority**: This protects data integrity for established installations but is only
exercised after real usage, so it can follow the initial country-selection story.

**Independent Test**: With Egypt applied and at least one posted journal entry in EGP, change the
country to the neutral country. Confirm the posted entry is untouched, the Egypt taxes and fiscal
positions still exist, the active defaults switch, and a currency-conflict warning is shown before
any currency change.

**Acceptance Scenarios**:

1. **Given** Egypt is applied with posted journal entries in EGP, **When** the administrator changes
   the country, **Then** all previously posted entries and invoices retain their original amounts,
   taxes, and currency.
2. **Given** a country change that implies a different functional currency and posted entries exist,
   **When** the administrator initiates the change, **Then** a warning is shown and the change does
   not proceed until they explicitly confirm.
3. **Given** the currency-conflict warning is shown, **When** the administrator declines, **Then** the
   country change is aborted and no currency, tax, fiscal-position, or default settings are modified.
4. **Given** a country is changed away from Egypt, **When** the change completes, **Then** the Egypt
   taxes and fiscal positions are retained in the system (they may be archived but are not deleted).
5. **Given** the company later switches back to a previously used country, **When** the package is
   re-applied, **Then** the previously created records are reused/reactivated rather than duplicated.
6. **Given** no accounting entries exist yet, **When** the country changes and implies a new currency,
   **Then** the functional currency switches without a warning.

---

### Edge Cases

- **Missing translation string**: a key with no value in the effective language falls back to the
  English source string; the UI never shows a blank or raw key.
- **Personal language no longer available**: if a user's stored personal language is not among the
  installed languages, their effective language falls back to the system default.
- **Neutral country selection**: selecting the no-package country (United Kingdom) leaves English and
  Arabic both installed and selectable, makes no currency/tax/fiscal-position changes, and retains
  existing company defaults.
- **Idempotent re-apply**: re-selecting the current country creates no duplicate currency, tax, or
  fiscal-position records; record counts are unchanged.
- **Currency change blocked**: a country change implying a new functional currency while posted
  entries exist requires explicit confirmation; declining leaves the system exactly as before.
- **Currency change with clean books**: the same change with no posted entries proceeds without a
  warning.
- **Number direction under RTL**: right-to-left layout does not reverse digit order within a number
  or the internal order of a date.
- **Anonymous/login screen**: before authentication the effective language is the system default.
- **New user via API without a language**: the user is assigned the system default language.
- **Concurrent Settings edits**: two administrators saving Settings at the same time resolve to a
  single consistent result; a stale save is rejected rather than silently overwriting.
- **Long translated strings in RTL**: labels that are much longer in one language must not break
  navigation or form layout.

## Requirements *(mandatory)*

### Functional Requirements

#### Language & translation

- **FR-001**: System MUST provide exactly two installed languages — Arabic (code `ar`) and English
  (code `en`) — as seeded reference data, each carrying its text direction (`ar` = right-to-left,
  `en` = left-to-right), decimal separator, thousands separator, and date format.
- **FR-002**: System MUST use Arabic as the system default language on a fresh install.
- **FR-003**: System MUST assign the current system default language to every newly created user that
  has no explicit language preference.
- **FR-004**: An administrator MUST be able to set the system-level default language, in Settings, to
  any installed language. The system default language MUST be stored as a `lang` value on the single
  company record.
- **FR-005**: Each user MUST be able to set a personal language preference that overrides the system
  default for their own session only.
- **FR-006**: System MUST resolve the effective language for a request as the requesting user's
  personal preference, falling back to the system default when the user has none (or has an
  uninstalled one).
- **FR-007**: System MUST serve all user-facing static text — field labels, menu items, button text,
  and system/validation/error messages — through a translation layer keyed by language code so it
  renders in the effective language.
- **FR-007a**: The server MUST resolve the effective language per request and return translated model
  field labels, model display names, and menu item labels within the existing metadata/RPC responses
  it already serves to the web client.
- **FR-007b**: The system MUST expose one read-only endpoint that returns the static client-string
  catalog (button text, validation/system/error messages, and other non-model UI text) for a given
  language; the web client loads this catalog once at bootstrap and reloads it when the effective
  language changes.
- **FR-007c**: Translation catalogs MUST be stored as static per-language files shipped with the
  localization addon and loaded into memory at startup; there is no database-backed translation
  record and no in-application translation-editing screen.
- **FR-008**: System MUST fall back to the English source string when a translation is missing for the
  effective language; it MUST NOT render a blank label or a raw translation key.
- **FR-009**: When the effective language is right-to-left (Arabic), the web UI MUST lay out
  right-to-left — text direction, text alignment, and mirrored navigation/menu placement — and
  left-to-right for a left-to-right language (English).
- **FR-010**: System MUST format numbers, dates, and monetary amounts shown in the UI according to the
  effective language's locale conventions (separators, date order, currency symbol placement),
  without altering digit order within a number.
- **FR-011**: A change to the system default language or to a user's personal language MUST take
  effect on that user's next request/page load without requiring re-login.
- **FR-012**: Only users with administrator privileges MUST be able to change the system default
  language; a personal language preference MUST be editable only by the user who owns it.

#### Country & reference data

- **FR-013**: System MUST provide a seeded list of countries, each with an ISO country code, a
  display name (translatable), a default currency code, and an international phone prefix.
- **FR-014**: System MUST provide seeded country states/subdivisions as reference data, each linked to
  its country (a minimal representative set is sufficient; an exhaustive worldwide list is not
  required).
- **FR-015**: Settings MUST expose a Country field for the company, selectable from the seeded country
  list, editable only by an administrator.
- **FR-016**: System MUST use Egypt as the company's default country on a fresh install.
- **FR-017**: System MUST seed United Kingdom (ISO `GB`, default currency GBP) as the "neutral"
  country that has no localization package, so a company can run with English and no country-driven
  tax/currency configuration. Selecting the neutral country MUST NOT create or change any tax, fiscal
  position, tax label, rounding method, default product tax, or the functional currency.

#### Country-driven localization

- **FR-018**: Selecting or changing the company country MUST apply that country's localization package
  when one exists.
- **FR-019**: Applying a localization package MUST set the company's functional currency to the
  country's default currency, creating and activating that currency record if it does not exist.
- **FR-020**: Applying a localization package MUST create the country's sales and purchase taxes at the
  correct rates when they are not already present, each mapped through its repartition to the
  appropriate tax accounts (tax collected for sales, tax deductible for purchases).
- **FR-021**: Applying a localization package MUST create the country's default fiscal positions — at
  minimum a domestic position and an export/foreign position — when they are not already present.
- **FR-022**: Applying a localization package MUST apply the country's document settings: the tax
  label shown on documents, the tax-amount rounding method, and the default sale tax and default
  purchase tax applied to newly created products.
- **FR-023**: Applying a localization package MUST set the package's taxes and domestic fiscal
  position as the active company defaults.
- **FR-024**: Applying a localization package MUST be idempotent — re-selecting the same country MUST
  NOT create duplicate currency, tax, or fiscal-position records.
- **FR-025**: On a fresh install the system MUST seed both languages (Arabic default), the country
  list including Egypt, set the company country to Egypt, and apply the Egypt localization package
  (EGP currency, taxes, fiscal positions, and defaults) with no manual steps.

#### Changing country with existing data

- **FR-026**: Changing the country when taxes, fiscal positions, or accounting entries already exist
  MUST NOT delete, deactivate, or modify any existing posted journal entry, posted invoice, or its
  tax lines.
- **FR-027**: Changing the country MUST add the new country's configuration alongside existing
  configuration and switch only the active defaults (default taxes, default fiscal position, tax
  label, rounding method).
- **FR-028**: If a country change would change the company's functional currency while posted
  accounting entries exist, the system MUST warn the administrator and require explicit confirmation
  before proceeding; if the administrator declines, the country change MUST be aborted with no
  currency, tax, fiscal-position, or default-setting side effects.
- **FR-029**: If a country change would change the functional currency and no posted accounting
  entries exist, the system MUST switch the currency without a warning.
- **FR-030**: Localization records (taxes, fiscal positions, currencies) from a previously applied
  country MUST be retained after switching countries — they MAY be archived/deactivated but MUST NOT
  be deleted.
- **FR-031**: Switching back to a previously applied country MUST reuse and reactivate the existing
  records for that package rather than creating duplicates.

#### Settings screen

- **FR-032**: The Settings screen MUST present the system language and the company country together
  and persist a save atomically (all requested changes apply together or none do).
- **FR-033**: The Settings save MUST carry the company record's last write timestamp; if that
  timestamp no longer matches the stored value (a concurrent change by another administrator), the
  save MUST be rejected and the administrator told to reload and retry, rather than silently
  overwriting the other change.

#### Egypt localization package (explicit contents)

- **FR-034**: The Egypt localization package MUST consist of exactly the following: the EGP currency
  (Egyptian Pound, symbol, rounding to 2 decimals); a "VAT 14%" sales tax (percentage, 14%); a
  "VAT 14%" purchase tax (percentage, 14%); a "VAT 0% (Exempt)" tax (percentage, 0%); a
  "VAT 0% (Export)" zero-rated tax (percentage, 0%); a "Domestic" fiscal position; an "Export" fiscal
  position; the document tax label "VAT"; the round-globally rounding method; and default
  new-product taxes of "VAT 14%" sales and "VAT 14%" purchase.
- **FR-035**: The Egypt "VAT 14%" sales tax MUST map to the VAT-collected account and the "VAT 14%"
  purchase tax MUST map to the VAT-deductible account from the existing default chart of accounts.
- **FR-036**: The Egypt "Export" fiscal position MUST map the "VAT 14%" sales and purchase taxes to
  the corresponding "VAT 0% (Export)" tax; the "Domestic" fiscal position applies no tax
  substitution.
- **FR-037**: The Egypt "VAT 0% (Exempt)" and "VAT 0% (Export)" taxes MUST both be created but are
  treated as distinct records (exempt vs. zero-rated) even though both carry a 0% rate.

### Key Entities *(include if feature involves data)*

- **Language**: an installed UI language. Attributes: code (`ar`/`en`), display name, text direction
  (right-to-left / left-to-right), decimal separator, thousands separator, date format, installed
  flag. Modelled on Odoo `res.lang`.
- **Translation catalog**: a set of static per-language files (one per installed language) shipped
  with the localization addon and loaded into memory at startup. Each entry is a (language code,
  string key/source, translated value) triple. Two consumption paths use it: (a) the server
  translates model field labels, model display names, and menu labels in its existing metadata/RPC
  responses; (b) a read-only endpoint returns the non-model client-string catalog that the web
  client loads at bootstrap. There is no database translation record and no translation-editing UI.
- **Country**: seeded reference data. Attributes: ISO code, name (translatable), default currency
  code, international phone prefix. Modelled on Odoo `res.country`. Related to **Country State**
  (code, name, parent country) modelled on Odoo `res.country.state`.
- **Settings**: the administrator-facing configuration surface (modelled on Odoo
  `res.config.settings`). Exposes: system default language, company country, and — derived from the
  active localization package — the document tax label, tax rounding method, and default product
  sale/purchase taxes.
- **User language preference**: a per-user optional language code stored on the user record; empty
  means "use system default".
- **Localization package**: a country-keyed definition of the currency, sales/purchase taxes, fiscal
  positions, and document settings to install when that country is chosen (modelled on Odoo `l10n_*`
  modules). The Egypt package is the only concrete package in scope.
- **Company** (reused, `res.company`): gains the system default language (`lang`), the selected
  country, the functional currency set by the package, the active tax label, rounding method, and
  default product taxes. Its last write timestamp is used for optimistic-concurrency checks on
  Settings saves.
- **Reused accounting entities**: `account.tax` (+ `account.tax.repartition.line`),
  `account.fiscal.position` (+ tax and account mapping lines), `res.currency`. The feature creates
  records in these existing models; it introduces no parallel tax/currency/fiscal structures.

### Security Requirements

- **SEC-001**: System MUST validate all inputs at system boundaries using whitelist-based validation —
  a submitted language code MUST be one of the installed language codes and a submitted country code
  MUST be one of the seeded country codes; anything else is rejected.
- **SEC-002**: System MUST enforce least-privilege access — only the administrator group may modify
  the system default language, the company country, or any localization-package record; the
  translation catalog is read-only to non-administrators.
- **SEC-003**: System MUST comply with OWASP Top 10; a checklist review is REQUIRED before
  implementation, with attention to injection (translation values, country/state seed data) and
  broken access control (Settings mutation endpoints).
- **SEC-004**: All Settings and localization mutation endpoints MUST require an authenticated
  administrator session; a personal language change MUST be restricted to the record of the
  requesting user.
- **SEC-005**: Translated strings MUST be rendered as text (escaped) so a translation value cannot
  inject markup or script into the UI.

### Performance Requirements

- **PERF-001**: Resolving the effective language and loading the translation catalog for a request
  MUST add < 50 ms overhead compared with serving the same request untranslated, under normal load.
- **PERF-002**: Applying a localization package (currency + up to four taxes + two fiscal positions +
  default settings) MUST complete in < 3 seconds.
- **PERF-003**: No known regressions permitted; benchmarks MUST run in CI for the language-resolution
  path, and the accounting module's existing targets (single-record retrieval < 500 ms, financial
  reports < 5 s) MUST be unaffected.

### Accessibility Requirements

- **ACC-001**: The UI MUST meet WCAG 2.1 AA colour-contrast ratios (≥ 4.5:1 normal text, ≥ 3:1 large
  text) in both right-to-left and left-to-right layouts.
- **ACC-002**: The language selector and the country field MUST be fully keyboard-navigable.
- **ACC-003**: Right-to-left layout MUST preserve a logical keyboard tab order, set the correct `lang`
  and `dir` attributes for assistive technology, and never convey an error state by colour alone.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After an administrator switches the system language, the entire visible UI (menus,
  labels, buttons, messages) renders in the new language within one page reload, with 100% of static
  strings either translated or shown via English fallback — zero missing or raw-key labels.
- **SC-002**: With Arabic active, 100% of the primary screens (login, home, list, form) render
  right-to-left with mirrored navigation; with English active, 100% render left-to-right.
- **SC-003**: A non-administrator user who sets a personal language different from the system default
  sees every subsequent screen in the personal language, while a concurrent user with no preference
  is unaffected — 0 cross-user language leakage.
- **SC-004**: On a fresh install, the company is configured for Egypt with EGP as functional currency
  and all four Egypt taxes plus both fiscal positions present and set as defaults, achieved with zero
  manual configuration steps.
- **SC-005**: Selecting Egypt on a company currently set to the neutral country applies the complete
  Egypt package in a single save action that completes in under 3 seconds.
- **SC-006**: Re-applying or switching countries never produces duplicate currency, tax, or
  fiscal-position records — record counts increase only by the genuinely new package's contents.
- **SC-007**: After any country change, 100% of previously posted journal entries and invoices retain
  their original amounts, taxes, and currency.
- **SC-008**: When posted entries exist and a country change implies a new functional currency, the
  administrator is warned and the change does not proceed without explicit confirmation — 0 silent
  functional-currency changes.
- **SC-009**: On 100% of sampled screens, dates and monetary amounts display with locale-correct
  formatting for the active language.
- **SC-010**: A newly created user with no language preference always resolves to the current system
  default language — verified across user creation via the Settings UI and via the data API.

## Assumptions

- The existing vanilla-JS single-page web client (the `web` addon) renders all screens and will
  consume server-translated model/menu metadata in existing responses, a client-string catalog from
  a dedicated endpoint loaded at bootstrap, and a direction flag exposed by the backend; no
  third-party internationalisation library is introduced.
- "Company/system level" language equals a single-company scope (multi-company is out of scope), so
  the system default language is stored once for the installation as the `lang` value on the single
  `res.company` record.
- Translation catalogs for Arabic and English are authored and shipped as static per-language JSON
  files with the addon, loaded into memory at startup, and cover only static UI strings; there is no
  database translation record or translation-editing UI, and user-entered business data is never
  auto-translated.
- The neutral country is United Kingdom (ISO `GB`), seeded with no localization package; English
  pairs naturally with it, but Arabic remains installed and selectable regardless of the selected
  country.
- The tax accounts the Egypt package maps to (VAT collected, VAT deductible) already exist in the
  default chart of accounts seeded by the accounting module; the feature does not add or template a
  chart of accounts.
- "Rounding method" values reuse the accounting module's existing tax-rounding options (round
  globally / round per line); Egypt uses round globally.
- Effective-language resolution happens server-side per request from the authenticated session user;
  the pre-authentication login screen uses the system default language.
- Date and number localisation uses each language's format fields (from the language reference data);
  no change of calendar system is implied (Gregorian dates are retained for Arabic).
- Egypt's seeded states are limited to a minimal representative set (e.g., a handful of governorates)
  sufficient as reference data.
- The feature depends on the completed accounting module (`account` addon) for `account.tax`,
  `account.fiscal.position`, `res.currency`, `res.company`, and the default chart of accounts, and on
  the completed web UI module for screen rendering.

## Out of Scope

- Additional languages beyond Arabic and English.
- Multi-company operation with companies in different countries.
- Automatic translation of user-entered business data (only static UI strings are translated).
- E-invoicing and tax-authority filing integration.
- Country-specific chart of accounts templates — the existing default chart of accounts is retained;
  only taxes, fiscal positions, and currency are country-driven.
- A full United Kingdom / England localization package or a fully featured generic "no localization"
  package — beyond leaving English plus a neutral country selectable, no such package is built.
