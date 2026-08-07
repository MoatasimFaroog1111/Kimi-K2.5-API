# Frontend Architecture

The browser application is split into independently replaceable components rather than a single monolithic script.

## Design direction

The visual system is intentionally Kimi-inspired: restrained surfaces, a narrow session sidebar, a centered conversation column, a compact model control near the composer, and a minimal chat/agent mode switch. No proprietary Kimi assets or source code are copied.

## SOLID boundaries

- **Single Responsibility**: storage, HTTP streaming, authentication, sidebar rendering, message rendering, composer behavior, notifications, and orchestration live in separate modules.
- **Open/Closed**: new model providers, storage adapters, or visual components can be introduced behind the same controller-facing behavior without rewriting the whole UI.
- **Liskov Substitution**: the controller depends on small behavioral contracts; compatible store/API/component implementations can replace the current ones.
- **Interface Segregation**: components expose only the operations the controller needs, such as `render`, `show`, `setBusy`, or `streamMessage`.
- **Dependency Inversion**: `ChatController` receives the store, API adapter, and UI components through constructor injection.

## Chat modules

- `app/static/chat/main.js` — composition root.
- `app/static/chat/controller.js` — application orchestration.
- `app/static/chat/store.js` — browser state and conversation persistence.
- `app/static/chat/api.js` — HTTP and NDJSON streaming adapter.
- `app/static/chat/constants.js` — stable UI configuration.
- `app/static/chat/utils.js` — pure formatting/helpers.
- `app/static/chat/components/auth.js` — gateway login dialog.
- `app/static/chat/components/sidebar.js` — sessions/search/export/delete navigation.
- `app/static/chat/components/header.js` — title, connection state, theme and lock controls.
- `app/static/chat/components/messages.js` — welcome, prompts, messages, code rendering and copy actions.
- `app/static/chat/components/composer.js` — prompt input, model selector and send behavior.
- `app/static/chat/components/toast.js` — transient notifications.
- `app/static/chat/components.css` — chat-component-specific CSS overrides.

## Agent integration

Agent Mode remains isolated under `app/static/agent`. It shares only stable DOM contracts with the chat shell: the composer, model selector, title, message region, mode switch, and toast. Switching modes emits a `kimi:mode-change` browser event so neither feature needs direct knowledge of the other's implementation.

## Compatibility

The existing localStorage/sessionStorage keys are preserved, so previous conversations and remembered gateway sessions continue to work after the redesign.
