// Closed display vocabulary. No authorization decisions or provider/Item access.
export function runSummary(run,fallback){
  const p=run?.operational_presentation;
  if(p?.profile!=='meupluggy_personal')return fallback;
  if(p.financial_collection_state==='COMPLETED'){
    return p.consent_state==='VALIDATED_AT_OBSERVATION'
      ?'Coleta financeira concluída · Associação do consentimento validada nesta observação; não comprova autorização atual.'
      :'Coleta financeira concluída · Consentimento não validado · Resultado geral: PARTIAL.';
  }
  return fallback;
}

export function consentNotice(diagnostic,fallback){
  if(diagnostic?.access_mode!=='meupluggy_personal')return fallback;
  if(diagnostic.audit_presentation_state==='VALIDATED_AT_OBSERVATION')return fallback;
  return 'Consentimento não validado'+(diagnostic.state==='ASSOCIATION_INCONSISTENT'
    ?' — associação inconsistente; registro rejeitado pela guarda de escopo. Nenhuma autorização atual foi confirmada.'
    :'. Nenhuma autorização atual foi confirmada por esta auditoria.');
}

export function collectionDiagnostic(checkpoint,diagnostics,fallback){
  // Scope this translation to the matching personal connection, including mixed views.
  if(checkpoint.resource==='consents'&&checkpoint.error_code==='ITEM_ID_DIFFERENT'&&diagnostics.some(d=>d.connection_id===checkpoint.connection_id&&d.access_mode==='meupluggy_personal')){
    return 'Consentimento não validado — associação inconsistente; registro rejeitado.';
  }
  return fallback;
}

// The catalog also names historical rows. Limit only operational choices.
export function activeConnections(catalog) {
  return catalog.connections.filter(connection => connection.enabled === true && connection.historical === false);
}

export function connectionLabel(connection, choices) {
  const name = connection.institution || 'Instituição indisponível';
  const peers = choices.filter(row => (row.institution || 'Instituição indisponível') === name);
  return name + (peers.length > 1 ? ' · Conexão ' + (peers.indexOf(connection) + 1) : '')
    + (connection.historical ? ' (histórica)' : '');
}
