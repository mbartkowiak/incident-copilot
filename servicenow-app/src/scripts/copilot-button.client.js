function showCopilot() {
    var modal = new GlideModal('glide_modal_confirm', true, 640);
    modal.setTitle('Incident Copilot');
    modal.renderWithContent('<p>Asking Incident Copilot…</p>');

    var ajax = new GlideAjax('x_67971_copilot.CopilotAjax');
    ajax.addParam('sysparm_name', 'getCopilot');
    ajax.addParam('sysparm_sys_id', g_form.getUniqueValue());
    ajax.getXMLAnswer(function (answer) {
        var data = {};
        try {
            data = JSON.parse(answer);
        } catch (e) {
            data = { error: 'Unexpected response from Incident Copilot.' };
        }
        modal.renderWithContent(render(data));
    });

    function esc(text) {
        return String(text === null || text === undefined ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function list(items) {
        var html = '<ul>';
        for (var i = 0; i < items.length; i++) html += '<li>' + esc(items[i]) + '</li>';
        return html + '</ul>';
    }

    function render(d) {
        if (d.error) return '<p>' + esc(d.error) + '</p>';
        var html = '<p><strong>' + esc(d.number) + '</strong> · ' + esc(d.state) + ' · ' + esc(d.priority) +
            ' · ' + esc(d.team || 'awaiting review') + '</p>';
        if (d.triage && d.triage.length) html += '<h4>Triage</h4>' + list(d.triage);
        if (d.sla) {
            html += '<h4>SLA</h4><p>' + esc(d.sla.elapsed_hours) + ' h of ' + esc(d.sla.target_hours) + ' h used' +
                (d.sla.breached ? ' (breached)' : '') + '. Tickets like this breach ' +
                esc(Math.round((d.risk ? d.risk.similar_rate : 0) * 100)) + '% of the time.</p>';
        }
        var s = d.summary;
        if (s) {
            html += '<h4>Summary (' + esc(d.model) + ')</h4><p><strong>' + esc(s.headline) + '</strong></p>' +
                '<p>' + esc(s.status) + '</p>' + list(s.actions_taken || []) +
                '<p><em>Next:</em> ' + esc(s.next_step) + '</p>';
            if (s.watch_outs && s.watch_outs.length) html += '<p><em>Watch out for:</em></p>' + list(s.watch_outs);
        } else {
            html += '<p>Summary unavailable right now.</p>';
        }
        return html;
    }
}
