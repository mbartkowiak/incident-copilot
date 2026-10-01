var CopilotAjax = Class.create();
CopilotAjax.prototype = Object.extendsObject(global.AbstractAjaxProcessor, {
    /**
     * The Copilot panel's data for one incident: the copilot's triage and Claude's summary.
     * Returns a JSON string. Only answers for incidents the current user can read.
     */
    getCopilot: function () {
        var sysId = this.getParameter('sysparm_sys_id');
        var incident = new GlideRecord('incident');
        if (!sysId || !incident.get(sysId) || !incident.canRead()) {
            return JSON.stringify({ error: 'Incident not found.' });
        }
        var number = String(incident.getValue('correlation_id') || '');
        if (number.indexOf('INC1') !== 0) {
            return JSON.stringify({ error: 'This incident is not linked to Incident Copilot yet.' });
        }
        var client = new CopilotClient();
        var ticket = client.getTicket(number);
        if (!ticket) {
            return JSON.stringify({ error: 'Incident Copilot is unavailable right now.' });
        }
        var summary = client.summarize(number);
        var notes = ticket.work_notes || [];
        var triage = [];
        for (var i = 0; i < notes.length; i++) {
            if (notes[i].author === 'Routing model') triage.push(notes[i].text);
        }
        return JSON.stringify({
            number: number,
            state: ticket.state,
            team: ticket.assignment_group,
            priority: ticket.priority_label,
            sla: ticket.sla,
            risk: ticket.risk,
            triage: triage,
            summary: summary ? summary.summary : null,
            model: summary ? summary.model : null,
        });
    },

    type: 'CopilotAjax',
});
