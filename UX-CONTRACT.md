# Rigdeck interaction contract

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Table Selection | native | Qt Quick Controls | Existing device lists | Keyboard focus |
| Select/Listbox | native | RigDeck/ComboBox.qml | Native Qt popup | Keyboard and selected item |
| Date | native | Qt locale | Read-only ISO analytics ranges | Snapshot validation |
| Form | ScreenStudio | studio.py validate and QML controls | Hardware forms keep their own backends | pytest validation and invalidation |
| Scrollbar | native | PageScroll.qml | Sidebar ScrollView | Narrow and desktop render |
| Toast | Main.qml | appState.toast | Existing module feedback | Hardware backend routing |
| CRUD | ScreenStudio | studio-draft.json and existing cooler backend | Explicit media upload/delete | Draft roundtrip and hardware file list |

## Screen Studio

Draft edits save locally and invalidate the rendered output. Render captures a validated draft, locks edits and writes only local temporary media. Failure releases the lock and retains the draft. Preview remains visible after editing but is labelled outdated. Send is enabled only for a valid render and a connected, idle cooler. It reuses the established uploader, storage check and carousel behavior. Rendering never writes hardware. Native file pickers filter supported media; missing/corrupt files produce persistent errors.

Traffic is an imported 28-day Search Console snapshot scoped to macdigital.ca. Its provenance and exact reporting dates appear in the interface and clip. No automatic refresh or realtime visitor count is implied. Local logo and analytics files are user data, never bundled in the public package. All pages retain lazy loading and adaptive hardware polling.

## Accessibility and resilience

All editor inputs have accessible names. Native control keyboard behavior is retained. Focus is visible. Reduced motion freezes the animated preview. The page owns one vertical scroll; narrow layout stacks editor below preview. Errors remain in context with a retry action. Draft saves are atomic. Missing analytics has an explicit empty state, not invented numbers.

The static web audit does not inspect QML; native Qt screenshots, interaction tests and backend tests are the applicable verification gates.
