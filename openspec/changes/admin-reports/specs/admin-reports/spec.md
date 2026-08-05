# Admin Reports Specification

## Purpose

Define a branch-scoped, read-only Reports area for administrators with client, prospect, monthly income, and monthly expense tables. Every report SHALL support the same loading, error, empty, filtering, and XLSX export conventions as the existing expense list.

## Requirements

### Requirement: Reports navigation and access
The admin UI MUST expose a Reports navigation group with separate routes for clients, prospects, income, and expenses. Backend access MUST require administrator authorization and active-branch scope.

#### Scenario: Administrator opens Reports
- GIVEN an authenticated administrator with an active branch
- WHEN the administrator selects Reports
- THEN the four report destinations are visible and each loads the selected report

#### Scenario: Unauthorized access is rejected
- GIVEN a user without administrator permission
- WHEN the user requests any report route or endpoint
- THEN access is denied and no report data is returned

#### Scenario: Branch isolation
- GIVEN an administrator selects branch A
- WHEN any report is loaded
- THEN every row belongs to branch A and records from branch B are excluded

### Requirement: Client report
The client report MUST be read-only and display first name, last name, CI, status, and last appointment date. It SHOULD support text search and status filtering.

#### Scenario: Client rows are displayed
- GIVEN clients exist for the active branch
- WHEN the client report loads
- THEN each row displays all five required fields

#### Scenario: No clients exist
- GIVEN the active branch has no clients
- WHEN the report loads
- THEN an explicit empty state is shown and export is unavailable

### Requirement: Prospect report
The prospect report MUST be read-only and display each prospect with its status and relevant identifying/contact data. It SHOULD support search and status filtering.

#### Scenario: Prospect rows are displayed
- GIVEN prospects exist for the active branch
- WHEN the prospect report loads
- THEN the table displays prospect identity, contact information, and status

### Requirement: Monthly income report
The income report MUST provide month/year selection and include ALL recorded payments in the selected period, with amount, client, service, date, time, status, and invoice PDF URL when available.

#### Scenario: All payments are included
- GIVEN recorded payments with any status exist in the selected month and active branch
- WHEN the income report loads
- THEN every matching payment is listed, including pending, approved, rejected, or cancelled records

#### Scenario: Invoice link is exported
- GIVEN a payment has an invoice PDF URL
- WHEN the administrator exports the income table to XLSX
- THEN the workbook contains the invoice URL as a usable hyperlink/value and does not claim to embed the PDF

### Requirement: Monthly expense report
The expense report MUST reproduce the existing gastos list behavior for the selected month/year, including branch scope, period controls, invoice links, read-only presentation, and XLSX export.

#### Scenario: Expenses are exported
- GIVEN expenses exist for the selected period
- WHEN the administrator exports the expense table
- THEN an XLSX workbook contains the visible expense columns and invoice URLs where available

### Requirement: Shared report states and export
Each report MUST show loading, API error, and empty states. XLSX export MUST represent the currently filtered/selected dataset and MUST be unavailable or clearly disabled when no rows exist.

#### Scenario: API failure
- GIVEN the report endpoint returns an error
- WHEN the report page renders
- THEN a user-visible error state is shown without stale or cross-branch data
