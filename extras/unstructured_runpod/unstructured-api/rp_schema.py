INPUT_VALIDATIONS = {
    'file_link': {
        'type': str,
        'required': True,
    },
    "mode": {
        'type': str,
        'required': False,
        'default' : "single"
    },
    "unstructured_args": {
        'type': dict,
        'required': False,
        'default' : {}
    }
}