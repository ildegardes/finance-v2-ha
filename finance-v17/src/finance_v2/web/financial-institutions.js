import {dateBR} from './privacy.js';
import {openFinanceError} from './open-finance-errors.js';
import {runSummary} from './open-finance-status.js';

const labels = {
  DRAFT: 'Rascunho', ACTIVE: 'Ativa', DISABLED: 'Desativada', ARCHIVED: 'Arquivada',
  IDLE: 'Sem coleta', RUNNING: 'Coleta em andamento', SUCCEEDED: 'Coleta concluída',
  FAILED: 'Falha registrada', INTERRUPTED: 'Coleta interrompida',
};
const messages = {
  PRIVATE_ADMIN_REQUIRED: 'Abra o Finance V17 pelo acesso privado configurado.',
  CONNECTION_CONFIGURATION_CHANGED: 'A conexão mudou. Atualize a lista antes de tentar novamente.',
  REPLACEMENT_DEPENDENCIES_PRESENT: 'A conexão antiga tem dados financeiros associados. A substituição exige análise.',
  AUDIT_RECONCILIATION_REQUIRED: 'Há uma auditoria pendente na conexão antiga.',
  CONNECTION_BINDING_ALREADY_REGISTERED: 'O vínculo já está cadastrado.',
  CONNECTION_BINDING_CHANGED: 'O Client ID informado não corresponde ao vínculo registrado.',
  ITEM_ID_DIFFERENT: 'O Item retornado pela Pluggy diverge do Item cadastrado.',
  ITEM_ENVIRONMENT_NOT_VERIFIED: 'O ambiente informado não corresponde ao Item retornado.',
  PROVIDER_VALIDATION_FAILED: 'A Pluggy não confirmou a conexão.',
  SYNC_BUSY: 'Há uma coleta ou um lease pendente nesta conexão.',
  DELETION_RETENTION_REQUIRED: 'O histórico ou as dependências exigem que a conexão permaneça arquivada.',
};

export async function showFinancialInstitutions({api, view, heading, navigation}) {
  heading('Instituições Financeiras', 'Gerencie conexões Pluggy e consulte o histórico de coleta.');
  const section = document.createElement('section');
  section.className = 'panel';
  section.innerHTML = `
    <div class="actions">
      <button type="button" data-add hidden>Adicionar instituição</button>
      <button type="button" class="secondary" data-refresh>Atualizar lista</button>
    </div>
    <p role="status" aria-live="polite" data-state>Carregando instituições…</p>
    <ul class="of-run-list" data-connections></ul>
    <form class="form-card" hidden autocomplete="off">
      <h2 data-form-title></h2>
      <div class="form-grid">
        <label>Nome da instituição<input data-field="label" required maxlength="200"></label>
        <label>Perfil<select data-field="environment">
          <option value="STRICT">Estrito</option><option value="PERSONAL">MeuPluggy pessoal</option>
          <option value="SANDBOX">Sandbox</option>
        </select></label>
        <label>Client ID<input type="password" data-field="client_id" required maxlength="512" autocomplete="off"></label>
        <label>Client Secret<input type="password" data-field="client_secret" required maxlength="512" autocomplete="new-password"></label>
        <label>Item ID<input type="password" data-field="item_id" required maxlength="200" autocomplete="off"></label>
      </div>
      <div class="actions"><button type="submit">Salvar rascunho</button>
        <button type="button" class="secondary" data-cancel>Cancelar</button></div>
    </form>
    <form class="form-card" data-delete-form hidden autocomplete="off">
      <h2>Excluir conexão arquivada</h2>
      <p>A exclusão remove o cadastro elegível e mantém o registro da ação na auditoria.</p>
      <label><input type="checkbox" data-backup required> Verifiquei que existe um backup atual e recuperável.</label>
      <label>Digite EXCLUIR DEFINITIVAMENTE<input data-delete-phrase required maxlength="23"></label>
      <div class="actions"><button type="submit">Excluir definitivamente</button>
        <button type="button" class="secondary" data-cancel-delete>Cancelar</button></div>
    </form>
    <form class="form-card" data-rotate-form hidden autocomplete="off">
      <h2>Trocar credenciais</h2>
      <p>A validação usa o mesmo Client ID e o Item já associado à conexão.</p>
      <div class="form-grid">
        <label>Client ID da conexão<input type="password" data-rotate-client required maxlength="512" autocomplete="off"></label>
        <label>Novo Client Secret<input type="password" data-rotate-secret required maxlength="512" autocomplete="new-password"></label>
      </div>
      <div class="actions"><button type="submit">Validar e salvar credenciais</button>
        <button type="button" class="secondary" data-cancel-rotate>Cancelar</button></div>
    </form>
    <form class="form-card" data-rename-form hidden>
      <h2>Editar nome da conexão</h2>
      <label>Novo nome<input data-new-label required maxlength="200"></label>
      <div class="actions"><button type="submit">Salvar nome</button>
        <button type="button" class="secondary" data-cancel-rename>Cancelar</button></div>
    </form>
    <section data-history hidden aria-label="Histórico da conexão"></section>`;
  view.append(section);
  const find = selector => section.querySelector(selector);
  const form = find('form'), status = find('[data-state]'), list = find('[data-connections]');
  const history = find('[data-history]'), add = find('[data-add]');
  const renameForm = find('[data-rename-form]');
  const rotateForm = find('[data-rotate-form]');
  const deleteForm = find('[data-delete-form]');
  let predecessor = null, renameTarget = null, rotateTarget = null, deleteTarget = null;
  let busy = false, writable = false;
  const current = () => section.isConnected && navigation.current();
  navigation.onDispose(() => { form.reset(); renameForm.reset(); rotateForm.reset(); });

  function button(label, action) {
    const result = document.createElement('button');
    result.type = 'button';
    result.textContent = label;
    result.onclick = () => { if (current() && !busy) action(); };
    return result;
  }

  function controls() {
    section.querySelectorAll('button').forEach(control => { control.disabled = busy; });
    add.hidden = !writable;
  }

  async function run(action) {
    if (busy || !current()) return;
    busy = true;
    controls();
    try {
      await action();
    } catch (error) {
      if (current()) status.textContent = Object.hasOwn(messages, error.code)
        ? messages[error.code] : 'Operação não confirmada. Atualize a lista antes de repetir.';
    } finally {
      busy = false;
      if (current()) controls();
    }
  }

  function closeForm() {
    form.reset();
    form.hidden = true;
    predecessor = null;
  }

  function openForm(row = null) {
    closeDelete();
    closeRename();
    closeRotate();
    closeForm();
    predecessor = row?.id ?? null;
    find('[data-form-title]').textContent = row ? 'Cadastrar conexão substituta' : 'Nova instituição';
    const label = find('[data-field="label"]');
    label.value = row?.institution ?? '';
    form.hidden = false;
    label.focus();
  }

  function closeRename() {
    renameForm.reset();
    renameForm.hidden = true;
    renameTarget = null;
  }

  function openRename(row) {
    closeDelete();
    closeForm();
    closeRotate();
    renameTarget = row;
    const label = find('[data-new-label]');
    label.value = row.institution;
    renameForm.hidden = false;
    label.focus();
  }

  function closeRotate() {
    rotateForm.reset();
    rotateForm.hidden = true;
    rotateTarget = null;
  }

  function openRotate(row) {
    closeDelete();
    closeForm();
    closeRename();
    rotateTarget = row;
    rotateForm.hidden = false;
    find('[data-rotate-client]').focus();
  }

  function closeDelete() {
    deleteForm.reset();
    deleteForm.hidden = true;
    deleteTarget = null;
  }

  function inspectDelete(row) {
    closeForm();
    closeRename();
    closeRotate();
    closeDelete();
    run(async () => {
      const report = await api('/open-finance/registry/delete/inspect', {method: 'POST', body: {
        connection_id: row.id, revision: row.revision,
      }});
      if (!current()) return;
      if (!report.eligible) {
        status.textContent = messages.DELETION_RETENTION_REQUIRED;
        return;
      }
      deleteTarget = row;
      status.textContent = 'Nenhuma dependência impeditiva foi encontrada.';
      deleteForm.hidden = false;
      find('[data-backup]').focus();
    });
  }

  async function load(message = '') {
    const payload = await api('/open-finance/connections');
    if (!current()) return;
    writable = payload.registry_admin_available === true;
    if (!writable) { closeForm(); closeRename(); closeRotate(); closeDelete(); }
    const rows = payload.connections;
    list.replaceChildren(...rows.map(row => {
      const li = document.createElement('li'), title = document.createElement('strong');
      const details = document.createElement('small'), actions = document.createElement('div');
      title.textContent = row.institution;
      const lifecycle = row.lifecycle || (row.enabled ? 'ACTIVE' : 'DISABLED');
      const latest = row.last_run;
      details.textContent = [
        labels[lifecycle], labels[row.sync_state],
        latest?.finished_at ? 'Última coleta: ' + dateBR(latest.finished_at) : '',
        latest?.operational_presentation ? runSummary(latest, '') : '',
        latest?.error_code ? openFinanceError(latest.error_code) : '',
      ].filter(Boolean).join(' · ');
      actions.className = 'actions';
      actions.append(button('Ver histórico', () => run(() => loadHistory(row, 1))));
      if (writable && ['DRAFT', 'DISABLED'].includes(lifecycle) && row.revision !== undefined) {
        actions.append(button(lifecycle === 'DRAFT' ? 'Validar e ativar' : 'Validar e reativar',
          () => change(row, 'activate', 'Validar o Item na Pluggy e habilitar a conexão?', 'Conexão ativada.')));
      }
      if (writable && row.revision !== undefined && ['ACTIVE', 'DISABLED', 'DRAFT'].includes(lifecycle)) {
        actions.append(button('Editar nome', () => openRename(row)));
        if (row.source === 'MANAGED') actions.append(button('Trocar credenciais', () => openRotate(row)));
        actions.append(button('Arquivar', () => change(row, 'archive',
          'Arquivar a conexão e preservar seu vínculo, dados e histórico?', 'Conexão arquivada.')));
        if (lifecycle === 'ACTIVE') {
          actions.append(button('Desativar', () => change(row, 'disable',
            'Suspender as coletas desta conexão e manter seus dados e histórico?', 'Conexão desativada.')));
        }
      }
      if (writable && lifecycle === 'ARCHIVED'
          && !rows.some(other => other.replaces_id === row.id && other.lifecycle !== 'ARCHIVED')) {
        actions.append(button('Cadastrar substituta', () => openForm(row)));
      }
      if (writable && lifecycle === 'ARCHIVED' && row.source === 'MANAGED') {
        actions.append(button('Verificar exclusão', () => inspectDelete(row)));
      }
      if (row.enabled && lifecycle === 'ACTIVE') {
        actions.append(button('Consultar cache Pluggy', () => {
          if (!window.confirm('Iniciar uma coleta manual dos dados disponíveis no cache da Pluggy?')) return;
          run(async () => {
            status.textContent = 'Coleta em andamento…';
            const result = await api('/open-finance/coverage-sync', {method: 'POST', body: {connection_id: row.id}});
            await load(runSummary(result.run, 'Coleta concluída. Confira o histórico.'));
          });
        }));
      }
      li.append(title, details, actions);
      return li;
    }));
    status.textContent = message || (!rows.length ? 'Nenhuma instituição cadastrada.'
      : writable ? '' : 'Administração disponível pelo acesso privado configurado.');
  }

  function change(row, action, confirmation, message) {
    if (!window.confirm(confirmation)) return;
    run(async () => {
      await api('/open-finance/registry/' + action, {method: 'POST', body: {
        connection_id: row.id, revision: row.revision, confirmed: true,
      }});
      if (current()) await load(message);
    });
  }

  async function loadHistory(row, page) {
    const query = new URLSearchParams({connection_id: row.id, page, page_size: 25});
    const result = await api('/open-finance/sync-runs?' + query);
    if (!current()) return;
    const title = document.createElement('h2'), entries = document.createElement('ul');
    title.textContent = 'Histórico de ' + row.institution;
    entries.className = 'of-run-list';
    entries.replaceChildren(...result.items.map(item => {
      const li = document.createElement('li');
      li.textContent = [dateBR(item.started_at), runSummary(item, labels[item.state]),
        item.error_code && openFinanceError(item.error_code)].filter(Boolean).join(' · ');
      return li;
    }));
    history.replaceChildren(title, entries);
    if (!result.items.length) entries.textContent = 'Nenhuma execução registrada.';
    if (page > 1) history.append(button('Página anterior', () => run(() => loadHistory(row, page - 1))));
    if (result.has_more) history.append(button('Próxima página', () => run(() => loadHistory(row, page + 1))));
    history.hidden = false;
  }

  add.onclick = () => openForm();
  find('[data-refresh]').onclick = () => run(() => load());
  find('[data-cancel]').onclick = closeForm;
  find('[data-cancel-rename]').onclick = closeRename;
  find('[data-cancel-rotate]').onclick = closeRotate;
  find('[data-cancel-delete]').onclick = closeDelete;
  deleteForm.onsubmit = event => {
    event.preventDefault();
    if (!writable || busy || !current() || !deleteTarget) return;
    const confirmation = find('[data-delete-phrase]').value;
    const backupConfirmed = find('[data-backup]').checked;
    if (!backupConfirmed || confirmation !== 'EXCLUIR DEFINITIVAMENTE') {
      status.textContent = 'Confirme o backup e digite a frase indicada.';
      return;
    }
    const body = {connection_id: deleteTarget.id, revision: deleteTarget.revision,
      backup_confirmed: true, confirmation};
    closeDelete();
    run(async () => {
      await api('/open-finance/registry/delete', {method: 'POST', body});
      if (current()) await load('Conexão excluída. A auditoria foi preservada.');
    });
  };
  rotateForm.onsubmit = event => {
    event.preventDefault();
    if (!writable || busy || !current() || !rotateTarget) return;
    if (!window.confirm('Validar as novas credenciais com a Pluggy e salvá-las para esta conexão?')) {
      closeRotate();
      return;
    }
    const body = {
      connection_id: rotateTarget.id, revision: rotateTarget.revision, confirmed: true,
      client_id: find('[data-rotate-client]').value, client_secret: find('[data-rotate-secret]').value,
    };
    closeRotate();
    run(async () => {
      await api('/open-finance/registry/rotate-credentials', {method: 'POST', body});
      if (current()) await load('Credenciais validadas e atualizadas.');
    });
  };
  renameForm.onsubmit = event => {
    event.preventDefault();
    if (!writable || busy || !current() || !renameTarget) return;
    const body = {connection_id: renameTarget.id, revision: renameTarget.revision,
      label: find('[data-new-label]').value};
    closeRename();
    run(async () => {
      await api('/open-finance/registry/rename', {method: 'POST', body});
      if (current()) await load('Nome atualizado.');
    });
  };
  form.onsubmit = event => {
    event.preventDefault();
    if (!writable || busy || !current()) return;
    const body = Object.fromEntries([...form.querySelectorAll('[data-field]')]
      .map(field => [field.dataset.field, field.value]));
    if (predecessor) body.replaces_id = predecessor;
    closeForm();
    run(async () => {
      await api('/open-finance/registry/drafts', {method: 'POST', body});
      if (current()) await load('Rascunho salvo. Valide o Item para ativar a conexão.');
    });
  };
  await run(() => load());
}
