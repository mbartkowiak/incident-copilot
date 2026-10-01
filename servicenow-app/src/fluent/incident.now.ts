import { BusinessRule, UiAction } from '@servicenow/sdk/core'

// New incidents raised in ServiceNow go to the copilot at once instead of waiting for its poll.
// Async so incident creation never waits on the network. Incidents the copilot created itself
// already carry its number in correlation_id, so they are skipped.
BusinessRule({
    $id: Now.ID['copilot-incident-event'],
    name: 'Send new incidents to Incident Copilot',
    table: 'incident',
    when: 'async',
    action: ['insert'],
    filterCondition: 'correlation_idISEMPTY',
    order: 1000,
    active: true,
    description: 'Reports each new incident to the Incident Copilot API for immediate AI triage.',
    script: Now.include('../scripts/copilot-event.server.js'),
})

// The copilot's triage, SLA view and an AI summary, on the incident form.
UiAction({
    $id: Now.ID['copilot-form-button'],
    name: 'Copilot',
    table: 'incident',
    actionName: 'x_67971_copilot_show',
    hint: 'Show Incident Copilot triage and an AI summary',
    condition: "String(current.getValue('correlation_id') || '').indexOf('INC1') == 0",
    showUpdate: true,
    showInsert: false,
    form: { showButton: true, style: 'primary' },
    // No isUi16Compatible: it maps to "List v3 Compatible", and with it set the classic form hides the button.
    client: { isClient: true, onClick: 'showCopilot()' },
    script: Now.include('../scripts/copilot-button.client.js'),
    order: 50,
})
