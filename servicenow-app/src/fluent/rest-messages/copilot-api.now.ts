import { RestMessage } from '@servicenow/sdk/core'

const API = 'https://d1fjhcqqwngd2n.cloudfront.net'

export const CopilotApi = RestMessage({
    $id: Now.ID['copilot-api'],
    name: 'Incident Copilot API',
    endpoint: API,
    description: 'Incident Copilot: AI triage, routing and summaries for incidents.',
    headers: [
        { $id: Now.ID['copilot-api-content-type'], name: 'Content-Type', value: 'application/json' },
        { $id: Now.ID['copilot-api-accept'], name: 'Accept', value: 'application/json' },
    ],
    functions: [
        {
            // Report a newly created incident so the copilot triages it immediately.
            name: 'postIncidentEvent',
            httpMethod: 'POST',
            endpoint: `${API}/api/servicenow/events`,
            content: '{"sys_id": "${sysId}"}',
            headers: [{ $id: Now.ID['copilot-api-event-secret'], name: 'X-Copilot-Secret', value: '${secret}' }],
            variables: [
                { $id: Now.ID['copilot-api-event-sysid'], name: 'sysId' },
                { $id: Now.ID['copilot-api-event-secret-var'], name: 'secret' },
            ],
        },
        {
            // The copilot's view of a linked ticket: triage, SLA, routing check.
            name: 'getTicket',
            httpMethod: 'GET',
            endpoint: `${API}/api/incidents/\${number}`,
            variables: [{ $id: Now.ID['copilot-api-ticket-number'], name: 'number' }],
        },
        {
            // Claude's handoff note (open ticket) or recap (resolved ticket), cached per version.
            name: 'summarizeTicket',
            httpMethod: 'POST',
            endpoint: `${API}/api/incidents/\${number}/summary`,
            content: '{}',
            variables: [{ $id: Now.ID['copilot-api-summary-number'], name: 'number' }],
        },
    ],
})
