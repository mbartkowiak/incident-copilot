import '@servicenow/sdk/global'

declare global {
    namespace Now {
        namespace Internal {
            interface Keys extends KeysRegistry {
                explicit: {
                    bom_json: {
                        table: 'sys_module'
                        id: 'a077e899efaf4550a72562afc4144beb'
                    }
                    'copilot-ajax': {
                        table: 'sys_script_include'
                        id: '3b80f9180ea043138631a5fbab94a966'
                    }
                    'copilot-api': {
                        table: 'sys_rest_message'
                        id: 'dd9714ec56be48ff94cd0c68539e1eac'
                    }
                    'copilot-api-accept': {
                        table: 'sys_rest_message_headers'
                        id: 'b44b4d73a19c44a79a07f4968029c7dc'
                    }
                    'copilot-api-content-type': {
                        table: 'sys_rest_message_headers'
                        id: 'aa256153664f41e7bcaf70f5fc2be398'
                    }
                    'copilot-api-event-secret': {
                        table: 'sys_rest_message_fn_headers'
                        id: '570c184efeb849e597410422c14e7f0d'
                    }
                    'copilot-api-event-secret-var': {
                        table: 'sys_rest_message_fn_parameters'
                        id: '9193738139bf407d91c61f4797cd5326'
                    }
                    'copilot-api-event-sysid': {
                        table: 'sys_rest_message_fn_parameters'
                        id: '8c99bfc9ef5b4aa8aa2f78607aabf5e8'
                    }
                    'copilot-api-summary-number': {
                        table: 'sys_rest_message_fn_parameters'
                        id: '1c45614e446d4e1c9e5f81a33d25ef3e'
                    }
                    'copilot-api-ticket-number': {
                        table: 'sys_rest_message_fn_parameters'
                        id: '8bb43aa7126b4849b89c0f7a899ee491'
                    }
                    'copilot-client': {
                        table: 'sys_script_include'
                        id: 'e257e683e3624b3f8ad166bcac5fa6ed'
                    }
                    'copilot-form-button': {
                        table: 'sys_ui_action'
                        id: 'a11a4ad866e24bdcb9f91e5a9bc8de32'
                    }
                    'copilot-incident-event': {
                        table: 'sys_script'
                        id: '4931b347a74646118c097ca2fd044f44'
                    }
                    'event-secret': {
                        table: 'sys_properties'
                        id: '797e8fa79ac4473fb8da1c705322e82b'
                    }
                    'events-enabled': {
                        table: 'sys_properties'
                        id: '2fd42a8fe06b4a9cb4feaa70dba544e0'
                    }
                    package_json: {
                        table: 'sys_module'
                        id: 'aac709955988481aaa045656e060ed6c'
                    }
                    'priv-properties': {
                        table: 'sys_scope_privilege'
                        id: 'a4e6de5383e34318e8035529feaad3a8'
                    }
                    'priv-read-incident': {
                        table: 'sys_scope_privilege'
                        id: '700b125f83e34318e8035529feaad3e2'
                    }
                    'priv-rest-body': {
                        table: 'sys_scope_privilege'
                        id: 'd8f6129383e34318e8035529feaad311'
                    }
                    'priv-rest-execute': {
                        table: 'sys_scope_privilege'
                        id: '38e6de5383e34318e8035529feaad3ec'
                    }
                    'priv-rest-param': {
                        table: 'sys_scope_privilege'
                        id: 'b4e6de5383e34318e8035529feaad3b3'
                    }
                    'priv-rest-status': {
                        table: 'sys_scope_privilege'
                        id: '10f6129383e34318e8035529feaad30e'
                    }
                    'priv-rest-timeout': {
                        table: 'sys_scope_privilege'
                        id: '7ce6de5383e34318e8035529feaad3e8'
                    }
                }
                composite: [
                    {
                        table: 'sys_rest_message_fn'
                        id: '44b77efbc0884b72abfd422650553de2'
                        key: {
                            rest_message: 'dd9714ec56be48ff94cd0c68539e1eac'
                            function_name: 'summarizeTicket'
                        }
                    },
                    {
                        table: 'sys_rest_message_fn'
                        id: '692ce46e65174385929f90640f780c2d'
                        key: {
                            rest_message: 'dd9714ec56be48ff94cd0c68539e1eac'
                            function_name: 'getTicket'
                        }
                    },
                    {
                        table: 'sys_rest_message_fn'
                        id: 'dc8006f37ab94eb0b177ea2bc6f4e5be'
                        key: {
                            rest_message: 'dd9714ec56be48ff94cd0c68539e1eac'
                            function_name: 'postIncidentEvent'
                        }
                    },
                ]
            }
        }
    }
}
