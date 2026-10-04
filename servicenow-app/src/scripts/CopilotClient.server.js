var CopilotClient = Class.create();
CopilotClient.prototype = {
    MESSAGE: 'Incident Copilot API',
    TIMEOUT_MS: 30000,

    initialize: function () {},

    _secret: function () {
        return gs.getProperty('x_67971_copilot.event_secret', '');
    },

    /** Report a new incident for immediate triage. Returns true when the API accepted it. */
    sendEvent: function (sysId) {
        var secret = this._secret();
        if (!secret) {
            gs.warn('Incident Copilot: event secret not set; skipping event for ' + sysId);
            return false;
        }
        var rm = new sn_ws.RESTMessageV2(this.MESSAGE, 'postIncidentEvent');
        rm.setStringParameterNoEscape('sysId', sysId);
        rm.setStringParameterNoEscape('secret', secret);
        return this._execute(rm, 'event ' + sysId) !== null;
    },

    /** The copilot's ticket (triage, SLA, routing check) for an app number such as INC1000004. */
    getTicket: function (number) {
        var rm = new sn_ws.RESTMessageV2(this.MESSAGE, 'getTicket');
        rm.setStringParameterNoEscape('number', number);
        rm.setStringParameterNoEscape('secret', this._secret());
        return this._execute(rm, 'ticket ' + number);
    },

    /** Claude's handoff note or recap for the ticket. */
    summarize: function (number) {
        var rm = new sn_ws.RESTMessageV2(this.MESSAGE, 'summarizeTicket');
        rm.setStringParameterNoEscape('number', number);
        rm.setStringParameterNoEscape('secret', this._secret());
        return this._execute(rm, 'summary ' + number);
    },

    _execute: function (rm, what) {
        rm.setHttpTimeout(this.TIMEOUT_MS);
        try {
            var response = rm.execute();
            var status = response.getStatusCode();
            if (status >= 200 && status < 300) {
                var body = response.getBody();
                return body ? JSON.parse(body) : {};
            }
            // Status only: response bodies may carry ticket text.
            gs.error('Incident Copilot ' + what + ' failed with HTTP ' + status);
        } catch (ex) {
            gs.error('Incident Copilot ' + what + ' failed: ' + ex.getMessage());
        }
        return null;
    },

    type: 'CopilotClient',
};
