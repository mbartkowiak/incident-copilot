import { CrossScopePrivilege } from '@servicenow/sdk/core'

// Runtime access the app needs outside its scope: reading incidents (Copilot button) and the
// outbound REST and property APIs (CopilotClient). Declared so installs work on instances that
// enforce cross-scope privileges instead of recording them on first use.

CrossScopePrivilege({
    $id: Now.ID['priv-read-incident'],
    operation: 'read',
    status: 'allowed',
    targetName: 'incident',
    targetScope: 'global',
    targetType: 'sys_db_object',
})

CrossScopePrivilege({
    $id: Now.ID['priv-properties'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'Glide API: properties',
    targetScope: 'global',
    targetType: 'scriptable',
})

CrossScopePrivilege({
    $id: Now.ID['priv-rest-execute'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'ScriptableRESTMessageClient.execute',
    targetScope: 'global',
    targetType: 'scriptable',
})

CrossScopePrivilege({
    $id: Now.ID['priv-rest-timeout'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'ScriptableRESTMessageClient.setHttpTimeout',
    targetScope: 'global',
    targetType: 'scriptable',
})

CrossScopePrivilege({
    $id: Now.ID['priv-rest-param'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'ScriptableRESTMessageClient.setStringParameterNoEscape',
    targetScope: 'global',
    targetType: 'scriptable',
})

CrossScopePrivilege({
    $id: Now.ID['priv-rest-status'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'ScriptableRESTResponse.getStatusCode',
    targetScope: 'global',
    targetType: 'scriptable',
})

CrossScopePrivilege({
    $id: Now.ID['priv-rest-body'],
    operation: 'execute',
    status: 'allowed',
    targetName: 'ScriptableRESTResponse.getBody',
    targetScope: 'global',
    targetType: 'scriptable',
})
