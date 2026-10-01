import { Property } from '@servicenow/sdk/core'

// Shared secret the Business Rule sends with incident events (X-Copilot-Secret). Installed empty:
// an admin sets it after install, so it never lives in source control or an update set.
Property({
    $id: Now.ID['event-secret'],
    name: 'x_67971_copilot.event_secret',
    type: 'password2',
    value: '',
    description: 'Shared secret sent to the Incident Copilot API with incident events. Must match SERVICENOW_WEBHOOK_SECRET on the API.',
    isPrivate: true,
    roles: { read: ['admin'], write: ['admin'] },
})

Property({
    $id: Now.ID['events-enabled'],
    name: 'x_67971_copilot.events_enabled',
    type: 'boolean',
    value: 'true',
    description: 'Send new incidents to the Incident Copilot API for triage as soon as they are created.',
})
