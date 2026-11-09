"""Additive display classification ONLY. Never grants access or writes state.

Raw run/checkpoint values stay unchanged. Evidence from another run cannot certify
an old run's consent. Only the explicitly configured personal profile is affected.
"""
import sqlite3

PROFILE='meupluggy_personal'


def personal(config):
    return getattr(config,'access_mode',None)==PROFILE


def presentation(c,config,run):
    if not personal(config):return None
    checkpoint=None
    try:
        if run.get('id'):
            checkpoint=c.execute("SELECT state,error_code,record_count FROM of_collection_checkpoints "
                                 "WHERE connection_id=? AND resource='consents' AND parent_id='' AND run_id=?",
                                 (config.id,run['id'])).fetchone()
    except sqlite3.Error:
        pass  # Missing display evidence is UNVERIFIED, never permission or failure of collection.
    state=run.get('state')
    financial={'SUCCEEDED':'COMPLETED','FAILED':'FAILED','INTERRUPTED':'INTERRUPTED','RUNNING':'RUNNING'}.get(state,'UNVERIFIED')
    raw_audit=run.get('consent_audit_state')
    raw_checkpoint=checkpoint['state'] if checkpoint is not None else None
    error=checkpoint['error_code'] if checkpoint is not None else None
    # Availability of an endpoint is not validation: EMPTY/403/404/missing evidence
    # cannot become a grant, and contradictory raw results cannot become valid.
    validated=(checkpoint is not None and raw_checkpoint=='COMPLETE' and checkpoint['record_count']>0
               and raw_audit not in ('FAILED','EMPTY','NOT_AUTHORIZED','NOT_AVAILABLE')
               and 'ITEM_ID_DIFFERENT' not in (run.get('warnings') or []))
    consent='VALIDATED_AT_OBSERVATION' if validated else 'UNVERIFIED'
    overall=('COMPLETED' if validated else 'PARTIAL') if financial=='COMPLETED' else financial
    safe_error=error if error in ('ITEM_ID_DIFFERENT','ACCOUNT_SCOPE_MISMATCH','CONSENT_NOT_ACTIVE','CONSENT_EXPIRED','AUTH_FAILED') else None
    return {'profile':PROFILE,'financial_collection_state':financial,'consent_state':consent,
            'overall_state':overall,'raw_consent_audit_state':raw_audit,
            'raw_checkpoint_state':raw_checkpoint,'raw_consent_error_code':safe_error,
            'evidence_basis':'SAME_RUN_CHECKPOINT' if checkpoint is not None else 'NOT_AVAILABLE_FOR_THIS_RUN',
            'profile_basis':'CURRENT_CONFIGURATION','authorization_state':'NOT_ESTABLISHED_BY_PRESENTATION'}


def present_run(c,config,run):
    if not personal(config):return run
    return {**run,'operational_presentation':presentation(c,config,run)}


def present_payload(c,settings,payload,operation):
    configs={cfg.id:cfg for cfg in settings.pluggy_connections}
    def run(value):
        cfg=configs.get(value.get('connection_id'))
        return present_run(c,cfg,value) if cfg is not None else value
    if 'run' in payload:payload={**payload,'run':run(payload['run'])}
    if 'runs' in payload:payload={**payload,'runs':[run(v) for v in payload['runs']]}
    if operation=='open_finance_runs' and 'items' in payload:
        payload={**payload,'items':[run(v) for v in payload['items']]}
    if 'connections' in payload:
        connections=[]
        for value in payload['connections']:
            cfg=configs.get(value.get('id'))
            if cfg is not None and personal(cfg):
                value={**value,'presentation_profile':PROFILE}
                if value.get('last_run'):value={**value,'last_run':run(value['last_run'])}
            connections.append(value)
        payload={**payload,'connections':connections}
    if 'consent_diagnostics' in payload:
        diagnostics=[]
        for value in payload['consent_diagnostics']:
            cfg=configs.get(value.get('connection_id'))
            if cfg is not None and personal(cfg):
                value={**value,'audit_presentation_state':'VALIDATED_AT_OBSERVATION' if value['state']=='ASSOCIATION_VALIDATED_IN_LAST_SCAN' else 'UNVERIFIED'}
            diagnostics.append(value)
        payload={**payload,'consent_diagnostics':diagnostics}
    return payload


def presentation_schema():
    text={'type':'string'};nullable={'type':['string','null']}
    return {'type':'object','additionalProperties':False,
            'required':['profile','financial_collection_state','consent_state','overall_state','raw_consent_audit_state',
                        'raw_checkpoint_state','raw_consent_error_code','evidence_basis','profile_basis','authorization_state'],
            'properties':{'profile':{'enum':[PROFILE]},'financial_collection_state':text,
                          'consent_state':{'enum':['UNVERIFIED','VALIDATED_AT_OBSERVATION']},'overall_state':text,
                          'raw_consent_audit_state':nullable,'raw_checkpoint_state':nullable,'raw_consent_error_code':nullable,
                          'evidence_basis':text,'profile_basis':{'enum':['CURRENT_CONFIGURATION']},
                          'authorization_state':{'enum':['NOT_ESTABLISHED_BY_PRESENTATION']}}}
