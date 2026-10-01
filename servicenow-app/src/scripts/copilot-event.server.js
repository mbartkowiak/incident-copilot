(function executeRule(current, previous) {
    if (gs.getProperty('x_67971_copilot.events_enabled', 'true') !== 'true') return;
    new CopilotClient().sendEvent(current.getUniqueValue());
})(current, previous);
