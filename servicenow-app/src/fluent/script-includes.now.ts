import { ScriptInclude } from '@servicenow/sdk/core'

export const CopilotClient = ScriptInclude({
    $id: Now.ID['copilot-client'],
    name: 'CopilotClient',
    description: 'Calls the Incident Copilot API: incident events, ticket triage, AI summaries.',
    script: Now.include('../scripts/CopilotClient.server.js'),
    accessibleFrom: 'package_private',
})

export const CopilotAjax = ScriptInclude({
    $id: Now.ID['copilot-ajax'],
    name: 'CopilotAjax',
    description: 'GlideAjax endpoint for the Copilot form button. Answers only for incidents the user can read.',
    script: Now.include('../scripts/CopilotAjax.server.js'),
    clientCallable: true,
    accessibleFrom: 'package_private',
})
