// Closed local vocabulary only: never display provider messages or payloads.
const messages = Object.freeze({
  AUTH_FAILED: 'Autenticação recusada pela Pluggy; o motivo não foi confirmado. Verifique o diagnóstico sanitizado antes de alterar credenciais.',
  INVALID_AUTH_RESPONSE: 'Resposta de autenticação inválida. Nenhuma chave válida foi confirmada.',
  ACCOUNT_SCOPE_MISMATCH: 'Recurso incompatível com o Item ou a conexão autorizada. A proteção de escopo bloqueou a coleta; não troque o Item sem verificar o vínculo.',
  TRANSACTION_SCOPE_MISMATCH: 'Movimentação incompatível com a conta autorizada. A proteção de escopo bloqueou a coleta.',
  CONNECTION_BINDING_CHANGED: 'O vínculo configurado difere do vínculo registrado. Verifique a associação antes de continuar.',
  CONSENT_EXPIRED: 'Consentimento expirado informado pelo provedor. Nenhuma renovação foi solicitada automaticamente.',
  CONSENT_NOT_ACTIVE: 'Nenhum consentimento ativo foi confirmado na resposta. Verifique a autorização existente antes de repetir.',
  ITEM_REAUTH_REQUIRED: 'O provedor informou necessidade de reautenticação da conexão. Nenhuma reconexão foi iniciada.',
  ITEM_USER_ACTION_REQUIRED: 'A conexão requer ação do titular segundo o provedor. Nenhuma ação foi executada automaticamente.',
  ITEM_UPDATING: 'O provedor informou que a conexão está em atualização. Consulte o histórico antes de repetir.',
  ITEM_STATUS_UNKNOWN: 'Estado da conexão não reconhecido. A coleta foi interrompida por segurança.',
  NETWORK_FAILURE: 'Falha de comunicação com o provedor. O resultado deve ser conferido no histórico antes de repetir.',
  TRANSIENT_EXHAUSTED: 'O provedor permaneceu indisponível ou limitou as consultas. Verifique o histórico antes de repetir.',
  PROVIDER_HTTP_ERROR: 'O provedor recusou a consulta ou retornou uma resposta inesperada. O motivo não foi confirmado.',
  INVALID_RESPONSE: 'Resposta do provedor incompatível com o contrato esperado. Nenhum resultado incompatível foi aceito.',
  RESPONSE_TOO_LARGE: 'Resposta do provedor acima do limite permitido. A coleta foi interrompida.',
  AUTO_SYNC_CANCELLED: 'Coleta interrompida. Os registros confirmados anteriormente permanecem no staging.',
  AUTO_SYNC_DEADLINE: 'O prazo da coleta terminou. Consulte a cobertura e o histórico antes de repetir.',
  INTERNAL_ERROR: 'Falha interna da coleta. Preserve o diagnóstico sanitizado para análise.',
  TRANSPORT_FAILURE: 'Falha no transporte da consulta. O motivo externo não foi confirmado.'
});
const known = code => typeof code === 'string' && Object.hasOwn(messages, code);
export function openFinanceError(code) {
  return known(code) ? messages[code] : 'Coleta não confirmada. Consulte o histórico e o diagnóstico sanitizado antes de repetir.';
}
export function coverageFailureCode(data) {
  const run = data?.run;
  return run && ['FAILED', 'INTERRUPTED'].includes(run.state) && known(run.error_code) ? run.error_code : undefined;
}
